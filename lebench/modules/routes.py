"""Route tracing — server→target (return path). Forward path needs external probes."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lebench.core.config_loader import find_config, load_config
from lebench.core.intensity_params import get_params
from lebench.core.platform import command_exists, run_command
from lebench.core.result import ModuleResult, ModuleStatus
from lebench.core.safety import CostEstimate
from lebench.modules.base import BenchmarkModule, ProbeResult, RunContext


def _targets(context: RunContext) -> Tuple[List[str], List[str]]:
    warnings: List[str] = []
    path = find_config(
        ["ping_targets.yaml", "ping_targets.yml", "ping_targets.json", "routes_targets.yaml"],
        search_dirs=[
            context.environment.get("config_dir") or ".",
            context.output_dir,
            ".",
            str(Path(__file__).resolve().parents[1] / "data"),
        ],
    )
    hosts: List[str] = []
    if path:
        try:
            data = load_config(path)
            for t in data.get("targets") or data.get("nodes") or []:
                if isinstance(t, dict) and t.get("host"):
                    hosts.append(str(t["host"]))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"config_error:{exc}")
    # Allow env override
    extra = context.environment.get("routes_targets")
    if isinstance(extra, list):
        hosts.extend(str(x) for x in extra)
    return list(dict.fromkeys(hosts)), warnings


def _parse_traceroute(text: str) -> List[Dict[str, Any]]:
    hops: List[Dict[str, Any]] = []
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)\s+(.+)", line)
        if not m:
            continue
        hop_no = int(m.group(1))
        rest = m.group(2)
        ip_m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", rest)
        rtts = [float(x) for x in re.findall(r"([0-9.]+)\s*ms", rest)]
        hops.append(
            {
                "hop": hop_no,
                "ip": ip_m.group(1) if ip_m else None,
                "rtt_ms": round(sum(rtts) / len(rtts), 3) if rtts else None,
                "raw": rest[:120],
            }
        )
    return hops


class RoutesModule(BenchmarkModule):
    name = "routes"
    description = "本机回程路由（traceroute/tracepath/mtr）；去程需外部探针"
    stage = "s3"
    implemented = True
    dependencies: List[str] = []
    optional_dependencies = ["traceroute", "tracepath", "mtr"]

    def probe(self, context: RunContext) -> ProbeResult:
        deps = {d: command_exists(d) for d in self.optional_dependencies}
        return ProbeResult(
            available=any(deps.values()),
            reason=None if any(deps.values()) else "missing_traceroute_tools",
            dependencies=deps,
        )

    def estimate_cost(self, context: RunContext) -> CostEstimate:
        p = get_params(context.intensity)
        return CostEstimate(time_sec=float(p.routes_timeout_sec), network_mb=0.2, notes=["outbound traceroute"])

    def run(self, context: RunContext) -> ModuleResult:
        started = time.monotonic()
        p = get_params(context.intensity)
        hosts, warnings = _targets(context)
        warnings.append("direction:return_path_server_to_target_only")
        warnings.append("forward_path_china_to_server:not_run_without_external_probe")

        if not hosts:
            return ModuleResult.not_run(
                reason="no_route_targets",
                conditions={
                    "forward_path": "not_run",
                    "return_path": "not_run",
                    "optimized": None,
                    "main_route_label": None,
                    "judgment_note": "线路优化结论留人工审核",
                },
                warnings=warnings,
                duration_sec=round(time.monotonic() - started, 3),
            )

        tool_name = None
        for cand in ("traceroute", "tracepath", "mtr"):
            if command_exists(cand):
                tool_name = cand
                break
        if not tool_name:
            return ModuleResult.not_run(
                reason="missing_traceroute_tools",
                warnings=warnings,
                duration_sec=round(time.monotonic() - started, 3),
            )

        traces: List[Dict[str, Any]] = []
        for host in hosts[:5]:
            if tool_name == "mtr":
                argv = ["mtr", "-r", "-c", "3", "-n", host]
            elif tool_name == "tracepath":
                argv = ["tracepath", "-n", host]
            else:
                argv = ["traceroute", "-n", "-m", str(p.routes_max_hops), host]
            code, out, err = run_command(argv, timeout=p.routes_timeout_sec)
            text = out or err or ""
            hops = _parse_traceroute(text)
            traces.append(
                {
                    "target": host if context.allow_sensitive else "<host>",
                    "tool": tool_name,
                    "exit_code": code,
                    "direction": "return_path",
                    "hops": hops if context.allow_sensitive else [
                        {**h, "ip": "<ip>" if h.get("ip") else None, "raw": "<redacted>"} for h in hops
                    ],
                }
            )

        duration = round(time.monotonic() - started, 3)
        metrics = {
            "traces": traces,
            "forward_path": "not_run",
            "optimized": None,
            "main_route_label": None,
            "judgment_note": "不具备外部探针；去程 not_run；优化结论留人工审核",
        }
        return ModuleResult(
            status=ModuleStatus.COMPLETED.value if traces else ModuleStatus.PARTIAL.value,
            metrics=metrics,
            tool={"name": tool_name, "version": None},
            conditions={
                "max_hops": p.routes_max_hops,
                "asn_lookup": "not_implemented_without_reliable_source",
            },
            warnings=warnings,
            duration_sec=duration,
        )
