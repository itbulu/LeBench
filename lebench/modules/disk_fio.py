"""FIO 4K random and 1M sequential benchmarks on a regular temp file."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lebench.core.intensity_params import get_params
from lebench.core.parseutil import tool_version
from lebench.core.platform import command_exists, free_space_bytes, run_command
from lebench.core.result import ModuleResult, ModuleStatus
from lebench.core.safety import CostEstimate, assert_safe_temp_file, is_blocked_write_path
from lebench.modules.base import BenchmarkModule, ProbeResult, RunContext


def _parse_size_mb(size: str) -> float:
    s = size.strip().upper()
    if s.endswith("G"):
        return float(s[:-1]) * 1024
    if s.endswith("M"):
        return float(s[:-1])
    if s.endswith("K"):
        return float(s[:-1]) / 1024
    return float(s) / (1024 * 1024)


def _job_metrics(job: Dict[str, Any], rw: str) -> Dict[str, Any]:
    """Extract MiB/s and IOPS from one fio JSON job."""
    section = "read" if "read" in rw else "write"
    # rw values: randread, randwrite, read, write
    if rw in {"randread", "read"}:
        section = "read"
    elif rw in {"randwrite", "write"}:
        section = "write"
    block = job.get(section) or {}
    bw_bytes = block.get("bw_bytes")
    bw_kib = block.get("bw")  # KiB/s historically
    iops = block.get("iops")
    lat = (block.get("lat_ns") or {}) if isinstance(block.get("lat_ns"), dict) else {}
    mib_s = None
    if isinstance(bw_bytes, (int, float)) and bw_bytes > 0:
        mib_s = round(float(bw_bytes) / (1024 * 1024), 3)
    elif isinstance(bw_kib, (int, float)):
        mib_s = round(float(bw_kib) / 1024.0, 3)
    return {
        "mib_s": mib_s,
        "iops": float(iops) if isinstance(iops, (int, float)) else None,
        "lat_ns_mean": lat.get("mean"),
        "unit_throughput": "MiB/s",
    }


class DiskFioModule(BenchmarkModule):
    name = "disk_fio"
    description = "FIO 4K 随机与 1M 顺序读写（临时文件）"
    stage = "s1"
    implemented = True
    dependencies = ["fio"]
    optional_dependencies: List[str] = []

    def probe(self, context: RunContext) -> ProbeResult:
        ok = command_exists("fio")
        p = get_params(context.intensity)
        free = free_space_bytes(context.work_dir)
        need = int(_parse_size_mb(p.fio_filesize) * 1.3 * 1024 * 1024)
        space_ok = free is None or free >= need
        return ProbeResult(
            available=ok and space_ok,
            reason=(
                None
                if ok and space_ok
                else ("missing_dependencies:fio" if not ok else "insufficient_free_space")
            ),
            dependencies={"fio": ok},
            details={"free_bytes": free, "need_bytes": need},
        )

    def estimate_cost(self, context: RunContext) -> CostEstimate:
        p = get_params(context.intensity)
        return CostEstimate(
            time_sec=float(p.fio_runtime_sec * 4 + 20),
            disk_write_mb=_parse_size_mb(p.fio_filesize),
            risks=["disk_write", "high_io"],
            notes=["4 jobs: rand4k r/w + seq1m r/w"],
        )

    def _run_one(
        self,
        *,
        name: str,
        filename: Path,
        rw: str,
        bs: str,
        params,
        ioengine: str,
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        argv = [
            "fio",
            f"--name={name}",
            f"--filename={filename}",
            f"--rw={rw}",
            f"--bs={bs}",
            f"--size={params.fio_filesize}",
            f"--runtime={params.fio_runtime_sec}",
            "--time_based",
            f"--iodepth={params.fio_iodepth}",
            f"--numjobs={params.fio_numjobs}",
            f"--ioengine={ioengine}",
            "--direct=1",
            "--group_reporting",
            "--output-format=json",
        ]
        code, out, err = run_command(
            argv,
            timeout=params.fio_runtime_sec + 120,
            max_stdout=512_000,
        )
        if code != 0:
            return {"ok": False, "exit_code": code, "stderr": (err or "")[:300]}, err
        try:
            data = json.loads(out or "{}")
        except json.JSONDecodeError:
            return {"ok": False, "exit_code": code, "stderr": "json_parse_error"}, "json_parse_error"
        jobs = data.get("jobs") or []
        if not jobs:
            return {"ok": False, "exit_code": code, "stderr": "no_jobs"}, "no_jobs"
        extracted = _job_metrics(jobs[0], rw)
        extracted.update({"ok": True, "exit_code": 0, "rw": rw, "bs": bs, "argv": argv})
        return extracted, None

    def run(self, context: RunContext) -> ModuleResult:
        started = time.monotonic()
        p = get_params(context.intensity)
        warnings: List[str] = []
        temp = Path(context.work_dir) / f"lebench-fio-{os.getpid()}.bin"

        try:
            assert_safe_temp_file(temp)
        except PermissionError as exc:
            return ModuleResult.permission_denied(reason=str(exc), duration_sec=0.0)
        if is_blocked_write_path(temp):
            return ModuleResult.failed(reason="blocked_path", duration_sec=0.0)

        free = free_space_bytes(context.work_dir)
        need = int(_parse_size_mb(p.fio_filesize) * 1.3 * 1024 * 1024)
        if free is not None and free < need:
            return ModuleResult.not_run(
                reason="insufficient_free_space",
                conditions={"free_bytes": free, "need_bytes": need},
                duration_sec=round(time.monotonic() - started, 3),
            )

        ioengine = p.fio_ioengine
        # Fallback engines for environments without libaio
        engines_try = [ioengine, "psync", "sync"]
        engines_try = list(dict.fromkeys(engines_try))

        jobs_spec = [
            ("rand_4k_read", "randread", "4k"),
            ("rand_4k_write", "randwrite", "4k"),
            ("seq_1m_read", "read", "1m"),
            ("seq_1m_write", "write", "1m"),
        ]

        metrics: Dict[str, Any] = {}
        raw_jobs: Dict[str, Any] = {}
        used_engine = None

        for job_name, rw, bs in jobs_spec:
            result = None
            last_err = None
            for eng in engines_try:
                result, last_err = self._run_one(
                    name=job_name,
                    filename=temp,
                    rw=rw,
                    bs=bs,
                    params=p,
                    ioengine=eng,
                )
                if result.get("ok"):
                    used_engine = eng
                    break
                if eng == ioengine and last_err:
                    warnings.append(f"fio_engine_{eng}_failed_try_fallback")
            if not result or not result.get("ok"):
                warnings.append(f"fio_job_failed:{job_name}:{last_err}")
                raw_jobs[job_name] = result or {"ok": False}
                continue
            raw_jobs[job_name] = {k: v for k, v in result.items() if k != "argv"}
            prefix = job_name
            metrics[f"{prefix}_mibs"] = result.get("mib_s")
            metrics[f"{prefix}_iops"] = result.get("iops")
            metrics[f"{prefix}_lat_ns_mean"] = result.get("lat_ns_mean")
            # Friendly aliases for scoring fallback chain
            if job_name == "seq_1m_read":
                metrics["seq_1m_read_mibs"] = result.get("mib_s")
                metrics["seq_1m_read_unit"] = "MiB/s"
            if job_name == "rand_4k_read":
                metrics["rand_4k_read_mibs"] = result.get("mib_s")
                metrics["rand_4k_read_iops"] = result.get("iops")

        # Cleanup
        try:
            if temp.exists():
                temp.unlink()
        except OSError as exc:
            warnings.append(f"temp_cleanup_failed:{exc}")

        conditions = {
            "filesize": p.fio_filesize,
            "runtime_sec": p.fio_runtime_sec,
            "iodepth": p.fio_iodepth,
            "numjobs": p.fio_numjobs,
            "ioengine": used_engine or ioengine,
            "direct": 1,
            "path_kind": "regular_temp_file",
            "unit_note": "内部吞吐为 MiB/s；网站 *_mbs 历史约定由适配器处理，禁止悄然混用",
            "jobs": raw_jobs,
        }
        duration = round(time.monotonic() - started, 3)
        tool = {"name": "fio", "version": tool_version("fio")}

        ok_count = sum(1 for v in raw_jobs.values() if isinstance(v, dict) and v.get("ok"))
        if ok_count == 0:
            return ModuleResult.failed(
                reason="fio_all_jobs_failed",
                metrics=metrics,
                conditions=conditions,
                warnings=warnings,
                tool=tool,
                duration_sec=duration,
            )
        status = (
            ModuleStatus.COMPLETED.value if ok_count == len(jobs_spec) else ModuleStatus.PARTIAL.value
        )
        return ModuleResult(
            status=status,
            metrics=metrics,
            tool=tool,
            conditions=conditions,
            duration_sec=duration,
            warnings=warnings,
        )
