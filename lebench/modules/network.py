"""Bounded download/upload speed tests against whitelisted configured nodes."""

from __future__ import annotations

import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lebench.core.config_loader import find_config, load_config
from lebench.core.intensity_params import get_params
from lebench.core.result import ModuleResult, ModuleStatus
from lebench.core.safety import CostEstimate
from lebench.modules.base import BenchmarkModule, ProbeResult, RunContext

VALID_OPERATORS = {"telecom", "unicom", "mobile", "international"}


def _search_dirs(context: RunContext) -> List[str]:
    dirs = [
        context.output_dir,
        ".",
        str(Path(context.output_dir).resolve().parent),
        str(Path(__file__).resolve().parents[1] / "data"),
    ]
    extra = context.environment.get("config_dir")
    if extra:
        dirs.insert(0, str(extra))
    return dirs


def _load_nodes(context: RunContext) -> Tuple[List[Dict[str, Any]], Optional[str], List[str]]:
    warnings: List[str] = []
    path = find_config(
        [
            "speedtest_targets.yaml",
            "speedtest_targets.yml",
            "speedtest_targets.json",
        ],
        search_dirs=_search_dirs(context),
    )
    # Fall back to packaged example only to discover schema — nodes usually disabled
    if not path:
        path = find_config(
            ["speedtest_targets.example.yaml"],
            search_dirs=_search_dirs(context),
        )
    if not path:
        return [], None, ["no_speedtest_targets_config"]
    try:
        data = load_config(path)
    except Exception as exc:  # noqa: BLE001
        return [], str(path), [f"config_load_error:{exc}"]
    nodes = data.get("nodes") or []
    if not isinstance(nodes, list):
        return [], str(path), ["nodes_not_a_list"]
    enabled = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        if n.get("enabled", True) is False:
            continue
        url = n.get("url") or n.get("download_url")
        if not url:
            warnings.append(f"node_missing_url:{n.get('name')}")
            continue
        op = str(n.get("operator", "international")).lower()
        if op not in VALID_OPERATORS:
            warnings.append(f"invalid_operator:{op}")
            op = "international"
        enabled.append(
            {
                "name": n.get("name") or "unnamed",
                "region": n.get("region"),
                "operator": op,
                "url": url,
                "upload_url": n.get("upload_url"),
            }
        )
    return enabled, str(path), warnings


def _download_probe(url: str, max_bytes: int, timeout: float) -> Dict[str, Any]:
    started = time.perf_counter()
    downloaded = 0
    first_byte_at = None
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "LeBench/0.1 (+benchmark; bounded)"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            while downloaded < max_bytes:
                chunk = resp.read(min(65536, max_bytes - downloaded))
                if not chunk:
                    break
                if first_byte_at is None:
                    first_byte_at = time.perf_counter()
                downloaded += len(chunk)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"{type(exc).__name__}:{exc}",
            "downloaded_bytes": downloaded,
            "elapsed_sec": round(time.perf_counter() - started, 4),
        }
    elapsed = time.perf_counter() - started
    # Mbps = bits / seconds / 1e6
    mbps = (downloaded * 8) / elapsed / 1_000_000 if elapsed > 0 else None
    latency_ms = None
    if first_byte_at is not None:
        latency_ms = round((first_byte_at - started) * 1000, 2)
    return {
        "ok": downloaded > 0,
        "downloaded_bytes": downloaded,
        "elapsed_sec": round(elapsed, 4),
        "download_mbps": round(mbps, 3) if mbps is not None else None,
        "latency_ms": latency_ms,
    }


def _upload_probe(url: str, max_bytes: int, timeout: float) -> Dict[str, Any]:
    payload = b"0" * min(max_bytes, 1_000_000)  # cap single request body
    # For larger budget, loop a few posts
    total = 0
    started = time.perf_counter()
    try:
        while total < max_bytes and (time.perf_counter() - started) < timeout:
            remain = max_bytes - total
            body = payload if remain >= len(payload) else b"0" * remain
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "User-Agent": "LeBench/0.1 (+benchmark; bounded)",
                    "Content-Type": "application/octet-stream",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp.read(1024)
            total += len(body)
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - started
        return {
            "ok": False,
            "error": f"{type(exc).__name__}:{exc}",
            "uploaded_bytes": total,
            "elapsed_sec": round(elapsed, 4),
        }
    elapsed = time.perf_counter() - started
    mbps = (total * 8) / elapsed / 1_000_000 if elapsed > 0 else None
    return {
        "ok": total > 0,
        "uploaded_bytes": total,
        "elapsed_sec": round(elapsed, 4),
        "upload_mbps": round(mbps, 3) if mbps is not None else None,
    }


class NetworkModule(BenchmarkModule):
    name = "network"
    description = "白名单节点有界测速（无节点则 not_run，不虚构三网成绩）"
    stage = "s2"
    implemented = True
    dependencies: List[str] = []
    optional_dependencies: List[str] = []

    def probe(self, context: RunContext) -> ProbeResult:
        nodes, path, _ = _load_nodes(context)
        # Available even with 0 nodes — run() returns not_run
        return ProbeResult(
            available=True,
            reason=None if nodes else "no_enabled_nodes",
            details={"config": path, "node_count": len(nodes)},
        )

    def estimate_cost(self, context: RunContext) -> CostEstimate:
        p = get_params(context.intensity)
        nodes, _, _ = _load_nodes(context)
        n = max(1, len(nodes))
        return CostEstimate(
            time_sec=float(p.network_timeout_sec * n),
            network_mb=min(p.network_max_total_mb, p.network_max_mb_per_node * n),
            risks=["network_traffic"],
            notes=["requires speedtest_targets.yaml with enabled urls"],
        )

    def run(self, context: RunContext) -> ModuleResult:
        started = time.monotonic()
        p = get_params(context.intensity)
        nodes, path, warnings = _load_nodes(context)
        # Prefer user config over example
        if path and path.endswith(".example.yaml") and not nodes:
            pass

        if not nodes:
            return ModuleResult.not_run(
                reason="no_speedtest_nodes_configured",
                conditions={
                    "config": path,
                    "hint": "复制 lebench/data/speedtest_targets.example.yaml 为 speedtest_targets.yaml 并填写可信节点",
                    "direction": "server_outbound_to_node",
                },
                warnings=warnings,
                duration_sec=round(time.monotonic() - started, 3),
                tool={"name": "lebench.network", "version": "0.1.0"},
            )

        budget_left = float(p.network_max_total_mb)
        results: List[Dict[str, Any]] = []
        for node in nodes:
            if budget_left <= 1:
                warnings.append("network_budget_exhausted")
                break
            per = min(p.network_max_mb_per_node, budget_left)
            max_bytes = int(per * 1024 * 1024)
            dl = _download_probe(node["url"], max_bytes=max_bytes, timeout=p.network_timeout_sec)
            used_mb = (dl.get("downloaded_bytes") or 0) / (1024 * 1024)
            budget_left -= used_mb

            upload = None
            if node.get("upload_url") and budget_left > 1:
                up_budget = min(per / 2, budget_left)
                upload = _upload_probe(
                    node["upload_url"],
                    max_bytes=int(up_budget * 1024 * 1024),
                    timeout=p.network_timeout_sec,
                )
                budget_left -= (upload.get("uploaded_bytes") or 0) / (1024 * 1024)

            entry = {
                "name": node["name"],
                "region": node.get("region"),
                "operator": node["operator"],
                "download_mbps": dl.get("download_mbps"),
                "upload_mbps": (upload or {}).get("upload_mbps"),
                "latency_ms": dl.get("latency_ms"),
                "ok": bool(dl.get("ok")),
                "error": dl.get("error") or (upload or {}).get("error"),
                "tool": "urllib",
                "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            results.append(entry)
            if not entry["ok"]:
                warnings.append(f"node_failed:{node['name']}")

        duration = round(time.monotonic() - started, 3)
        ok_nodes = [r for r in results if r.get("ok")]
        metrics = {
            "nodes": results,
            "download_peak_mbps": max((r["download_mbps"] for r in ok_nodes if r.get("download_mbps")), default=None),
            "budget_remaining_mb": round(budget_left, 2),
        }
        conditions = {
            "config": path,
            "direction": "server_outbound_to_node",
            "max_mb_per_node": p.network_max_mb_per_node,
            "max_total_mb": p.network_max_total_mb,
            "timeout_sec": p.network_timeout_sec,
            "note": "不要将网卡链路速率当作真实互联网带宽；无节点时不得虚构三网成绩",
        }
        tool = {"name": "lebench.network.urllib", "version": "0.1.0"}

        if not ok_nodes:
            return ModuleResult(
                status=ModuleStatus.FAILED.value,
                reason="all_nodes_failed",
                metrics=metrics,
                conditions=conditions,
                warnings=warnings,
                tool=tool,
                duration_sec=duration,
            )
        status = (
            ModuleStatus.COMPLETED.value
            if len(ok_nodes) == len(results)
            else ModuleStatus.PARTIAL.value
        )
        return ModuleResult(
            status=status,
            metrics=metrics,
            conditions=conditions,
            warnings=warnings,
            tool=tool,
            duration_sec=duration,
        )
