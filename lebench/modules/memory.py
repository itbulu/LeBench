"""Memory bandwidth via sysbench memory (throughput only unless tool provides latency)."""

from __future__ import annotations

import time
from typing import Any, Dict, List

from lebench.core.intensity_params import get_params
from lebench.core.parseutil import first_float, tool_version
from lebench.core.platform import command_exists, run_command
from lebench.core.result import ModuleResult, ModuleStatus
from lebench.core.safety import CostEstimate
from lebench.modules.base import BenchmarkModule, ProbeResult, RunContext


def _parse_size_to_mb(size: str) -> float:
    s = size.strip().upper()
    if s.endswith("G"):
        return float(s[:-1]) * 1024
    if s.endswith("M"):
        return float(s[:-1])
    if s.endswith("K"):
        return float(s[:-1]) / 1024
    return float(s) / (1024 * 1024)


class MemoryModule(BenchmarkModule):
    name = "memory"
    description = "内存带宽（sysbench memory；仅填写工具真实测出的项）"
    stage = "s1"
    implemented = True
    dependencies = ["sysbench"]
    optional_dependencies: List[str] = []

    def probe(self, context: RunContext) -> ProbeResult:
        ok = command_exists("sysbench")
        return ProbeResult(
            available=ok,
            reason=None if ok else "missing_dependencies:sysbench",
            dependencies={"sysbench": ok},
        )

    def estimate_cost(self, context: RunContext) -> CostEstimate:
        p = get_params(context.intensity)
        return CostEstimate(
            time_sec=30.0,
            cpu_heavy=True,
            notes=[f"sysbench memory total={p.memory_total_size}"],
        )

    def run(self, context: RunContext) -> ModuleResult:
        started = time.monotonic()
        p = get_params(context.intensity)
        warnings: List[str] = []
        metrics: Dict[str, Any] = {
            "read_gbps": None,
            "write_gbps": None,
            "copy_gbps": None,
            "latency_ns": None,
        }
        conditions: Dict[str, Any] = {
            "tool": "sysbench memory",
            "threads": p.memory_threads,
            "block_size": p.memory_block_size,
            "total_size": p.memory_total_size,
            "note": "sysbench memory 主要提供吞吐；未测出的延迟保持 null，禁止估算填入",
            "unit_note": "内部字段 *_gbps；网站 Schema 可能为 read_gb_s，由未来适配器转换",
        }

        # sysbench memory uses --memory-oper=write|read (copy not always available)
        results: Dict[str, Any] = {}
        for oper in ("read", "write"):
            argv = [
                "sysbench",
                "memory",
                f"--memory-block-size={p.memory_block_size}",
                f"--memory-total-size={p.memory_total_size}",
                f"--threads={p.memory_threads}",
                f"--memory-oper={oper}",
                "run",
            ]
            code, out, err = run_command(argv, timeout=180, max_stdout=64_000)
            text = (out or "") + "\n" + (err or "")
            # "transferred (X.XX MiB/sec)" or "X.XX MiB/sec"
            mibs = first_float(r"\(([0-9.]+)\s*MiB/sec\)", text)
            if mibs is None:
                mibs = first_float(r"([0-9.]+)\s*MiB/sec", text)
            # Also "transferred (X.XX MB/sec)" — convert carefully
            if mibs is None:
                mbs = first_float(r"\(([0-9.]+)\s*MB/sec\)", text)
                if mbs is not None:
                    # treat decimal MB/s → approx MiB/s then to GB/s binary? Prefer GiB/s from MiB
                    mibs = mbs * (1_000_000 / (1024 * 1024))
                    warnings.append(f"sysbench_{oper}_reported_MB_sec_converted_approx")
            gbps = round(mibs / 1024.0, 4) if mibs is not None else None
            results[oper] = {
                "ok": code == 0 and gbps is not None,
                "mib_s": mibs,
                "gbps": gbps,
                "exit_code": code,
                "argv": argv,
            }
            if results[oper]["ok"]:
                metrics[f"{oper}_gbps"] = gbps
                metrics[f"{oper}_mib_s"] = mibs
                metrics[f"{oper}_unit"] = "GiB/s_from_MiB/s"
            else:
                warnings.append(f"sysbench_memory_{oper}_failed")

        # copy: try if supported
        argv_copy = [
            "sysbench",
            "memory",
            f"--memory-block-size={p.memory_block_size}",
            f"--memory-total-size={p.memory_total_size}",
            f"--threads={p.memory_threads}",
            "--memory-oper=write",
            "--memory-access-mode=seq",
            "run",
        ]
        # Do not invent copy; leave null unless a dedicated oper exists in future
        conditions["copy"] = "not_measured_by_default_sysbench_profile"
        conditions["ops"] = {k: {"exit_code": v["exit_code"], "argv": v["argv"]} for k, v in results.items()}
        conditions["approx_working_set_mb"] = _parse_size_to_mb(p.memory_total_size)

        duration = round(time.monotonic() - started, 3)
        tool = {"name": "sysbench", "version": tool_version("sysbench")}

        if metrics["read_gbps"] is None and metrics["write_gbps"] is None:
            return ModuleResult.failed(
                reason="memory_benchmark_failed",
                warnings=warnings,
                conditions=conditions,
                tool=tool,
                duration_sec=duration,
            )

        status = (
            ModuleStatus.COMPLETED.value
            if metrics["read_gbps"] is not None and metrics["write_gbps"] is not None
            else ModuleStatus.PARTIAL.value
        )
        return ModuleResult(
            status=status,
            metrics=metrics,
            tool=tool,
            conditions=conditions,
            duration_sec=duration,
            warnings=warnings,
        )
