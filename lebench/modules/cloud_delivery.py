"""Cloud delivery capabilities — do not auto-call paid cloud APIs or fabricate timings."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List

from lebench.core.platform import command_exists
from lebench.core.result import ModuleResult, ModuleStatus
from lebench.core.safety import CostEstimate
from lebench.modules.base import BenchmarkModule, ProbeResult, RunContext


FEATURES = [
    "create_instance",
    "ssh_ready_time",
    "reinstall_os",
    "destroy_instance",
    "console_vnc",
    "rescue_mode",
]


class CloudDeliveryModule(BenchmarkModule):
    name = "cloud_delivery"
    description = "云化交付能力（首版不自动探测厂商 API、不编造耗时）"
    stage = "s4"
    implemented = True
    dependencies: List[str] = []
    optional_dependencies: List[str] = []

    def probe(self, context: RunContext) -> ProbeResult:
        return ProbeResult(available=True, details={"auto_cloud_api": False})

    def estimate_cost(self, context: RunContext) -> CostEstimate:
        return CostEstimate(time_sec=1.0, notes=["records not_run reasons only"])

    def run(self, context: RunContext) -> ModuleResult:
        started = time.monotonic()
        # Soft environment hints only — not product capability claims
        hints: Dict[str, Any] = {
            "cloud_init_present": Path("/etc/cloud").exists() or command_exists("cloud-init"),
            "systemd_present": Path("/run/systemd/system").exists(),
        }
        features: Dict[str, Any] = {}
        for f in FEATURES:
            features[f] = {
                "status": "not_run",
                "reason": "cloud_vendor_api_not_auto_probed",
                "value": None,
            }

        metrics = {
            "features": features,
            "environment_hints": hints,
        }
        conditions = {
            "auto_create_destroy": False,
            "note": "云 API 创建→SSH/重装/销毁耗时属于外部编排，首版不自动测量、不编造",
        }
        return ModuleResult(
            status=ModuleStatus.COMPLETED.value,
            metrics=metrics,
            conditions=conditions,
            warnings=["features_require_manual_or_external_orchestration"],
            tool={"name": "lebench.cloud_delivery", "version": "0.1.0"},
            duration_sec=round(time.monotonic() - started, 3),
        )
