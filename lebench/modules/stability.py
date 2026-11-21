"""Bounded latency/loss sampling over a short window — not a 7x24 SLA claim."""

from __future__ import annotations

import statistics
import time
from typing import Any, Dict, List, Optional

from lebench.core.intensity_params import get_params
from lebench.core.result import ModuleResult, ModuleStatus
from lebench.core.safety import CostEstimate
from lebench.modules.base import BenchmarkModule, ProbeResult, RunContext
from lebench.modules.ping import _icmp_ping, _load_targets, _tcp_ping


class StabilityModule(BenchmarkModule):
    name = "stability"
    description = "有界时长延迟/丢包采样与统计摘要（不声称 7×24 SLA）"
    stage = "s3"
    implemented = True
    dependencies: List[str] = []
    optional_dependencies = ["ping"]

    def probe(self, context: RunContext) -> ProbeResult:
        return ProbeResult(available=True)

    def estimate_cost(self, context: RunContext) -> CostEstimate:
        p = get_params(context.intensity)
        return CostEstimate(
            time_sec=float(p.stability_duration_sec),
            network_mb=0.5,
            notes=["bounded sampling only"],
        )

    def run(self, context: RunContext) -> ModuleResult:
        started = time.monotonic()
        p = get_params(context.intensity)
        targets, path, warnings = _load_targets(context)
        if not targets:
            return ModuleResult.not_run(
                reason="no_ping_targets_for_stability",
                conditions={"config": path, "sla_claim": False},
                warnings=warnings,
                duration_sec=round(time.monotonic() - started, 3),
            )

        target = targets[0]
        host = target["host"]
        proto = target.get("protocol") or "icmp"
        series: List[Dict[str, Any]] = []
        deadline = time.monotonic() + p.stability_duration_sec

        while time.monotonic() < deadline and not context.cancel_requested:
            if proto == "tcp":
                sample = _tcp_ping(host, int(target.get("port") or 80), 1, p.ping_timeout_sec)
            else:
                sample = _icmp_ping(host, 1, p.ping_timeout_sec)
            series.append(
                {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "avg_ms": sample.get("avg_ms"),
                    "ok": sample.get("ok"),
                    "loss_pct": sample.get("loss_pct"),
                }
            )
            time.sleep(max(0.2, p.stability_interval_sec))

        ok_vals = [s["avg_ms"] for s in series if s.get("ok") and s.get("avg_ms") is not None]
        loss_events = sum(1 for s in series if not s.get("ok"))
        summary = {
            "samples": len(series),
            "success": len(ok_vals),
            "loss_events": loss_events,
            "loss_pct_approx": round(100.0 * loss_events / len(series), 2) if series else None,
            "avg_ms": round(statistics.mean(ok_vals), 3) if ok_vals else None,
            "min_ms": round(min(ok_vals), 3) if ok_vals else None,
            "max_ms": round(max(ok_vals), 3) if ok_vals else None,
            "stdev_ms": round(statistics.pstdev(ok_vals), 3) if len(ok_vals) > 1 else None,
        }
        duration = round(time.monotonic() - started, 3)
        return ModuleResult(
            status=ModuleStatus.COMPLETED.value if ok_vals else ModuleStatus.PARTIAL.value,
            metrics={
                "target_name": target.get("name"),
                "summary": summary,
                "series": series,
            },
            conditions={
                "duration_sec": p.stability_duration_sec,
                "interval_sec": p.stability_interval_sec,
                "sla_claim": False,
                "note": "有界采样，不声称 7×24 SLA",
                "config": path,
            },
            warnings=warnings + ["not_a_sla_guarantee"],
            tool={"name": "lebench.stability", "version": "0.1.0"},
            duration_sec=duration,
        )
