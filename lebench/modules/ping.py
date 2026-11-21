"""Outbound ICMP/TCP ping against configured targets."""

from __future__ import annotations

import socket
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lebench.core.config_loader import find_config, load_config
from lebench.core.intensity_params import get_params
from lebench.core.parseutil import first_float
from lebench.core.platform import command_exists, run_command
from lebench.core.result import ModuleResult, ModuleStatus
from lebench.core.safety import CostEstimate
from lebench.modules.base import BenchmarkModule, ProbeResult, RunContext


def _search_dirs(context: RunContext) -> List[str]:
    dirs = [
        context.output_dir,
        ".",
        str(Path(__file__).resolve().parents[1] / "data"),
    ]
    extra = context.environment.get("config_dir")
    if extra:
        dirs.insert(0, str(extra))
    return dirs


def _load_targets(context: RunContext) -> Tuple[List[Dict[str, Any]], Optional[str], List[str]]:
    warnings: List[str] = []
    path = find_config(
        [
            "ping_targets.yaml",
            "ping_targets.yml",
            "ping_targets.json",
            "ping_targets.example.yaml",
        ],
        search_dirs=_search_dirs(context),
    )
    if not path:
        return [], None, ["no_ping_targets_config"]
    try:
        data = load_config(path)
    except Exception as exc:  # noqa: BLE001
        return [], str(path), [f"config_load_error:{exc}"]
    targets = data.get("targets") or []
    enabled = []
    for t in targets:
        if not isinstance(t, dict):
            continue
        if t.get("enabled", True) is False:
            continue
        host = t.get("host") or t.get("target")
        if not host:
            warnings.append(f"target_missing_host:{t.get('name')}")
            continue
        enabled.append(
            {
                "name": t.get("name") or host,
                "region": t.get("region"),
                "operator": t.get("operator"),
                "host": host,
                "protocol": str(t.get("protocol", "icmp")).lower(),
                "port": t.get("port") or 80,
                "samples": t.get("samples"),
            }
        )
    return enabled, str(path), warnings


def _icmp_ping(host: str, samples: int, timeout: float) -> Dict[str, Any]:
    if not command_exists("ping"):
        return {"ok": False, "error": "ping_command_missing", "protocol": "icmp"}
    # Linux: ping -c N -W timeout_sec
    # Busybox may differ; try Linux style first
    timeout_ms = max(1, int(timeout * 1000))
    argv = ["ping", "-c", str(samples), "-W", str(int(timeout)), host]
    code, out, err = run_command(argv, timeout=samples * (timeout + 1) + 10)
    text = (out or "") + "\n" + (err or "")
    if code != 0 and "unknown" in text.lower():
        argv = ["ping", "-n", str(samples), "-w", str(timeout_ms), host]
        code, out, err = run_command(argv, timeout=samples * (timeout + 1) + 10)
        text = (out or "") + "\n" + (err or "")

    # rtt min/avg/max/mdev = 1.2/3.4/5.6/0.7 ms
    avg = first_float(r"rtt [^=]+=\s*[0-9.]+/([0-9.]+)/", text)
    min_v = first_float(r"rtt [^=]+=\s*([0-9.]+)/", text)
    max_v = first_float(r"rtt [^=]+=\s*[0-9.]+/[0-9.]+/([0-9.]+)/", text)
    loss = first_float(r"([0-9.]+)%\s*packet loss", text)
    if avg is None:
        # Windows style Average = 12ms
        avg = first_float(r"Average\s*=\s*([0-9.]+)ms", text)
        min_v = first_float(r"Minimum\s*=\s*([0-9.]+)ms", text)
        max_v = first_float(r"Maximum\s*=\s*([0-9.]+)ms", text)
        loss = first_float(r"\(([0-9.]+)%\s*loss\)", text)

    icmp_blocked = code != 0 and avg is None and (
        "operation not permitted" in text.lower()
        or "permission" in text.lower()
        or "filtered" in text.lower()
    )
    return {
        "ok": avg is not None,
        "protocol": "icmp",
        "avg_ms": avg,
        "min_ms": min_v,
        "max_ms": max_v,
        "loss_pct": loss,
        "samples": samples,
        "exit_code": code,
        "icmp_possibly_blocked": icmp_blocked,
        "error": None if avg is not None else ("icmp_blocked_or_failed" if icmp_blocked else "ping_failed"),
    }


def _tcp_ping(host: str, port: int, samples: int, timeout: float) -> Dict[str, Any]:
    rtts: List[float] = []
    failures = 0
    for _ in range(samples):
        t0 = time.perf_counter()
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                pass
            rtts.append((time.perf_counter() - t0) * 1000)
        except OSError:
            failures += 1
    if not rtts:
        return {
            "ok": False,
            "protocol": "tcp",
            "error": "tcp_connect_failed",
            "loss_pct": 100.0,
            "samples": samples,
            "port": port,
        }
    return {
        "ok": True,
        "protocol": "tcp",
        "port": port,
        "avg_ms": round(statistics.mean(rtts), 3),
        "min_ms": round(min(rtts), 3),
        "max_ms": round(max(rtts), 3),
        "loss_pct": round(100.0 * failures / samples, 2),
        "samples": samples,
    }


class PingModule(BenchmarkModule):
    name = "ping"
    description = "对可审计目标做 ICMP/TCP 出站延迟与丢包测试"
    stage = "s2"
    implemented = True
    dependencies: List[str] = []
    optional_dependencies = ["ping"]

    def probe(self, context: RunContext) -> ProbeResult:
        targets, path, _ = _load_targets(context)
        return ProbeResult(
            available=True,
            reason=None if targets else "no_enabled_targets",
            dependencies={"ping": command_exists("ping")},
            details={"config": path, "target_count": len(targets)},
        )

    def estimate_cost(self, context: RunContext) -> CostEstimate:
        p = get_params(context.intensity)
        return CostEstimate(time_sec=float(p.ping_samples * 2), network_mb=0.1, notes=["outbound ping"])

    def run(self, context: RunContext) -> ModuleResult:
        started = time.monotonic()
        p = get_params(context.intensity)
        targets, path, warnings = _load_targets(context)
        if not targets:
            return ModuleResult.not_run(
                reason="no_ping_targets_configured",
                conditions={
                    "config": path,
                    "direction": "server_outbound_to_target",
                    "hint": "复制 ping_targets.example.yaml 为 ping_targets.yaml",
                    "note": "出站 Ping ≠ 国内三网入站延迟",
                },
                warnings=warnings,
                duration_sec=round(time.monotonic() - started, 3),
                tool={"name": "lebench.ping", "version": "0.1.0"},
            )

        nodes: List[Dict[str, Any]] = []
        for t in targets:
            samples = int(t.get("samples") or p.ping_samples)
            proto = t["protocol"]
            if proto == "tcp":
                result = _tcp_ping(t["host"], int(t.get("port") or 80), samples, p.ping_timeout_sec)
            else:
                result = _icmp_ping(t["host"], samples, p.ping_timeout_sec)
                if result.get("icmp_possibly_blocked"):
                    warnings.append(
                        f"icmp_blocked:{t['name']} — 不能直接认定网络不可达，可改用 protocol: tcp"
                    )
            nodes.append(
                {
                    "name": t["name"],
                    "region": t.get("region"),
                    "operator": t.get("operator"),
                    "host": t["host"] if context.allow_sensitive else "<host>",
                    **result,
                    "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                }
            )

        ok_nodes = [n for n in nodes if n.get("ok")]
        duration = round(time.monotonic() - started, 3)
        metrics = {
            "nodes": nodes,
            "avg_ms_mean": (
                round(statistics.mean([n["avg_ms"] for n in ok_nodes if n.get("avg_ms") is not None]), 3)
                if ok_nodes
                else None
            ),
        }
        conditions = {
            "config": path,
            "direction": "server_outbound_to_target",
            "note": "从服务器主动 Ping 属于出站测量，不等于国内用户侧入站延迟",
        }
        tool = {"name": "lebench.ping", "version": "0.1.0"}
        if not ok_nodes:
            return ModuleResult(
                status=ModuleStatus.FAILED.value,
                reason="all_ping_targets_failed",
                metrics=metrics,
                conditions=conditions,
                warnings=warnings,
                tool=tool,
                duration_sec=duration,
            )
        status = (
            ModuleStatus.COMPLETED.value if len(ok_nodes) == len(nodes) else ModuleStatus.PARTIAL.value
        )
        return ModuleResult(
            status=status,
            metrics=metrics,
            conditions=conditions,
            warnings=warnings,
            tool=tool,
            duration_sec=duration,
        )
