"""CPU benchmark — Sysbench primary; optional Geekbench if installed."""

from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional

from lebench.core.intensity_params import get_params
from lebench.core.parseutil import first_float, first_str, tool_version
from lebench.core.platform import command_exists, run_command
from lebench.core.result import ModuleResult, ModuleStatus
from lebench.core.safety import CostEstimate
from lebench.modules.base import BenchmarkModule, ProbeResult, RunContext


def _auto_threads(requested: int) -> int:
    if requested and requested > 0:
        return requested
    return max(1, os.cpu_count() or 1)


def _run_sysbench_cpu(threads: int, max_prime: int, time_sec: int) -> Dict[str, Any]:
    argv = [
        "sysbench",
        "cpu",
        f"--cpu-max-prime={max_prime}",
        f"--threads={threads}",
        f"--time={time_sec}",
        "run",
    ]
    code, out, err = run_command(argv, timeout=time_sec + 60, max_stdout=128_000)
    text = (out or "") + "\n" + (err or "")
    eps = first_float(r"events per second:\s*([0-9.]+)", text)
    total_events = first_float(r"total number of events:\s*([0-9.]+)", text)
    return {
        "ok": code == 0 and eps is not None,
        "exit_code": code,
        "events_per_sec": eps,
        "total_events": total_events,
        "raw_excerpt": "\n".join(text.splitlines()[:40]),
        "argv": argv,
    }


def _find_geekbench() -> Optional[str]:
    for name in ("geekbench6", "geekbench", "geekbench5"):
        if command_exists(name):
            return name
    return None


def _run_geekbench(bin_name: str, work_dir: str) -> Dict[str, Any]:
    """Run Geekbench if present. Never download/embed binaries."""
    argv = [bin_name, "--cpu"]
    code, out, err = run_command(argv, timeout=900, max_stdout=256_000, cwd=work_dir)
    text = (out or "") + "\n" + (err or "")
    # Official-ish text patterns; also HTML/result links vary by version
    single = first_float(r"Single-Core Score\s*[:=]?\s*([0-9]+)", text)
    multi = first_float(r"Multi-Core Score\s*[:=]?\s*([0-9]+)", text)
    if single is None:
        single = first_float(r"单核[^0-9]*([0-9]+)", text)
    if multi is None:
        multi = first_float(r"多核[^0-9]*([0-9]+)", text)
    version = first_str(r"Geekbench\s+([0-9.]+)", text) or tool_version(bin_name)
    tests: List[Dict[str, Any]] = []
    if single is not None:
        tests.append({"tool": "Geekbench", "name": "单核", "score": int(single), "unit": "score"})
    if multi is not None:
        tests.append({"tool": "Geekbench", "name": "多核", "score": int(multi), "unit": "score"})
    return {
        "ok": code == 0 and bool(tests),
        "exit_code": code,
        "version": version,
        "tests": tests,
        "raw_excerpt": "\n".join(text.splitlines()[:60]),
    }


class CpuModule(BenchmarkModule):
    name = "cpu"
    description = "CPU 基准（Sysbench 默认；可选本机已安装的 Geekbench）"
    stage = "s1"
    implemented = True
    dependencies = ["sysbench"]
    optional_dependencies = ["geekbench6", "geekbench"]

    def probe(self, context: RunContext) -> ProbeResult:
        deps = {
            "sysbench": command_exists("sysbench"),
            "geekbench": bool(_find_geekbench()),
        }
        if not deps["sysbench"] and not (
            context.environment.get("enable_geekbench") and deps["geekbench"]
        ):
            return ProbeResult(
                available=False,
                reason="missing_dependencies:sysbench",
                dependencies=deps,
            )
        return ProbeResult(available=True, dependencies=deps)

    def estimate_cost(self, context: RunContext) -> CostEstimate:
        p = get_params(context.intensity)
        return CostEstimate(
            time_sec=float(p.cpu_time_sec + 5),
            cpu_heavy=True,
            risks=["high_cpu_load"],
            notes=["sysbench cpu; optional geekbench if enabled and installed"],
        )

    def run(self, context: RunContext) -> ModuleResult:
        started = time.monotonic()
        params = get_params(context.intensity)
        threads = _auto_threads(params.cpu_threads)
        warnings: List[str] = []
        tests: List[Dict[str, Any]] = []
        metrics: Dict[str, Any] = {}
        conditions: Dict[str, Any] = {
            "intensity": context.intensity,
            "params": {
                "threads": threads,
                "cpu_max_prime": params.cpu_max_prime,
                "time_sec": params.cpu_time_sec,
            },
        }

        sysbench_ver = tool_version("sysbench") if command_exists("sysbench") else None
        tool_meta: Dict[str, Any] = {"name": "sysbench", "version": sysbench_ver}

        if command_exists("sysbench"):
            sb = _run_sysbench_cpu(threads, params.cpu_max_prime, params.cpu_time_sec)
            conditions["sysbench_argv"] = sb["argv"]
            if sb["ok"]:
                metrics["sysbench_events_per_sec"] = sb["events_per_sec"]
                metrics["sysbench_total_events"] = sb["total_events"]
                metrics["sysbench_threads"] = threads
                tests.append(
                    {
                        "tool": "Sysbench",
                        "name": "cpu_events_per_sec",
                        "score": sb["events_per_sec"],
                        "unit": "events_per_sec",
                        "threads": threads,
                        "time_sec": params.cpu_time_sec,
                        "cpu_max_prime": params.cpu_max_prime,
                    }
                )
                warnings.append(
                    "Sysbench 数值不可伪装为 Geekbench 分数；网站 CPU 维仅认 Geekbench/单核"
                )
            else:
                warnings.append(f"sysbench_failed:exit={sb['exit_code']}")
        else:
            warnings.append("sysbench_not_found")

        # Optional Geekbench — only if user enabled AND binary exists (no download)
        gb_bin = _find_geekbench()
        enable_gb = bool(context.environment.get("enable_geekbench"))
        if enable_gb and gb_bin:
            gb = _run_geekbench(gb_bin, context.work_dir)
            conditions["geekbench_bin"] = gb_bin
            conditions["geekbench_version"] = gb.get("version")
            if gb["ok"]:
                tests.extend(gb["tests"])
                metrics["geekbench_tests"] = gb["tests"]
            else:
                warnings.append(f"geekbench_failed:exit={gb['exit_code']}")
        elif enable_gb and not gb_bin:
            warnings.append("geekbench_enabled_but_not_installed")
            metrics["geekbench"] = "not_run"
        else:
            metrics["geekbench"] = "not_run"
            conditions["geekbench"] = "not_run_unless_--enable-geekbench_and_installed"

        metrics["tests"] = tests
        duration = round(time.monotonic() - started, 3)

        if not tests:
            return ModuleResult.failed(
                reason="no_cpu_benchmark_results",
                warnings=warnings,
                conditions=conditions,
                tool=tool_meta,
                duration_sec=duration,
            )

        status = ModuleStatus.COMPLETED.value
        if "sysbench_events_per_sec" not in metrics and not any(
            t.get("tool") == "Geekbench" for t in tests
        ):
            status = ModuleStatus.PARTIAL.value

        return ModuleResult(
            status=status,
            metrics=metrics,
            tool=tool_meta,
            conditions=conditions,
            duration_sec=duration,
            warnings=warnings,
        )
