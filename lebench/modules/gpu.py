"""GPU detection via nvidia-smi / rocm-smi. No large model benchmarks by default."""

from __future__ import annotations

import csv
import io
import re
import time
from typing import Any, Dict, List

from lebench.core.platform import command_exists, run_command
from lebench.core.result import ModuleResult, ModuleStatus
from lebench.core.safety import CostEstimate
from lebench.modules.base import BenchmarkModule, ProbeResult, RunContext


def _nvidia() -> Dict[str, Any]:
    argv = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version,temperature.gpu,power.draw,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    code, out, err = run_command(argv, timeout=20)
    if code != 0:
        return {"ok": False, "error": (err or out or "")[:200]}
    gpus = []
    reader = csv.reader(io.StringIO(out or ""))
    for row in reader:
        if len(row) < 6:
            continue
        gpus.append(
            {
                "name": row[0].strip(),
                "memory_total_mb": _to_float(row[1]),
                "driver_version": row[2].strip(),
                "temperature_c": _to_float(row[3]),
                "power_w": _to_float(row[4]),
                "utilization_pct": _to_float(row[5]),
                "vendor": "nvidia",
            }
        )
    # CUDA version
    code2, out2, _ = run_command(["nvidia-smi"], timeout=15)
    cuda = None
    if code2 == 0 and out2:
        m = re.search(r"CUDA Version:\s*([0-9.]+)", out2)
        cuda = m.group(1) if m else None
    return {"ok": True, "gpus": gpus, "cuda_version": cuda}


def _rocm() -> Dict[str, Any]:
    code, out, err = run_command(["rocm-smi", "--showproductname", "--showmeminfo", "vram"], timeout=20)
    if code != 0:
        return {"ok": False, "error": (err or "")[:200]}
    return {
        "ok": True,
        "gpus": [{"name": "rocm_device", "raw_excerpt": (out or "")[:500], "vendor": "amd"}],
        "rocm": True,
    }


def _to_float(raw: str):
    try:
        return float(raw.strip())
    except ValueError:
        return None


class GpuModule(BenchmarkModule):
    name = "gpu"
    description = "GPU 型号/显存/驱动探测；默认不做大模型推理基准"
    stage = "s4"
    implemented = True
    dependencies: List[str] = []
    optional_dependencies = ["nvidia-smi", "rocm-smi"]

    def probe(self, context: RunContext) -> ProbeResult:
        deps = {d: command_exists(d) for d in self.optional_dependencies}
        return ProbeResult(
            available=any(deps.values()),
            reason=None if any(deps.values()) else "no_gpu_tools",
            dependencies=deps,
        )

    def estimate_cost(self, context: RunContext) -> CostEstimate:
        return CostEstimate(time_sec=5.0, notes=["nvidia-smi/rocm-smi probe only"])

    def run(self, context: RunContext) -> ModuleResult:
        started = time.monotonic()
        warnings: List[str] = [
            "no_large_model_download_by_default",
            "inference_throughput_not_claimed_without_explicit_benchmark",
        ]
        metrics: Dict[str, Any] = {}

        has_nv = command_exists("nvidia-smi")
        has_rocm = command_exists("rocm-smi")
        if not has_nv and not has_rocm:
            return ModuleResult.not_applicable(
                reason="no_gpu_tools_or_hardware_detected",
                warnings=warnings,
                duration_sec=round(time.monotonic() - started, 3),
                tool={"name": "lebench.gpu", "version": "0.1.0"},
            )

        gpus: List[Dict[str, Any]] = []
        if has_nv:
            nv = _nvidia()
            if nv.get("ok"):
                gpus.extend(nv.get("gpus") or [])
                metrics["cuda_version"] = nv.get("cuda_version")
            else:
                warnings.append(f"nvidia_smi_failed:{nv.get('error')}")
        if has_rocm and not gpus:
            rc = _rocm()
            if rc.get("ok"):
                gpus.extend(rc.get("gpus") or [])
            else:
                warnings.append(f"rocm_smi_failed:{rc.get('error')}")

        if not gpus:
            return ModuleResult.not_applicable(
                reason="gpu_tools_present_but_no_device",
                warnings=warnings,
                duration_sec=round(time.monotonic() - started, 3),
            )

        metrics["gpus"] = gpus
        metrics["gpu_count"] = len(gpus)
        metrics["compute_benchmark"] = "not_run"
        conditions = {
            "compute_benchmark": "not_run",
            "note": "计算/推理基准需显式工具、精度、模型、量化、batch 与成本预算",
        }
        duration = round(time.monotonic() - started, 3)
        return ModuleResult(
            status=ModuleStatus.COMPLETED.value,
            metrics=metrics,
            conditions=conditions,
            warnings=warnings,
            tool={"name": "nvidia-smi" if has_nv else "rocm-smi", "version": None},
            duration_sec=duration,
        )
