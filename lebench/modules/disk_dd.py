"""Controlled DD sequential write/read on a regular temp file only."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from lebench.core.intensity_params import get_params
from lebench.core.parseutil import first_float, tool_version
from lebench.core.platform import command_exists, free_space_bytes, run_command
from lebench.core.result import ModuleResult, ModuleStatus
from lebench.core.safety import CostEstimate, assert_safe_temp_file, is_blocked_write_path
from lebench.modules.base import BenchmarkModule, ProbeResult, RunContext


def _parse_dd_speed(text: str) -> Optional[float]:
    """Return MB/s (10^6) if possible from dd stderr."""
    # 123456789 bytes (123 MB, 117 MiB) copied, 1.2 s, 100 MB/s
    mbs = first_float(r"([0-9.]+)\s*MB/s", text)
    if mbs is not None:
        return mbs
    mibs = first_float(r"([0-9.]+)\s*MiB/s", text)
    if mibs is not None:
        return mibs * (1024 * 1024) / 1_000_000
    return None


class DiskDdModule(BenchmarkModule):
    name = "disk_dd"
    description = "受控 DD 顺序读写（仅普通临时文件，禁止块设备）"
    stage = "s1"
    implemented = True
    dependencies = ["dd"]
    optional_dependencies: List[str] = []

    def probe(self, context: RunContext) -> ProbeResult:
        ok = command_exists("dd")
        free = free_space_bytes(context.work_dir)
        p = get_params(context.intensity)
        need = int(p.dd_size_mb * 1.2 * 1024 * 1024)
        space_ok = free is None or free >= need
        return ProbeResult(
            available=ok and space_ok,
            reason=(
                None
                if ok and space_ok
                else ("missing_dependencies:dd" if not ok else "insufficient_free_space")
            ),
            dependencies={"dd": ok},
            details={"free_bytes": free, "need_bytes": need},
        )

    def estimate_cost(self, context: RunContext) -> CostEstimate:
        p = get_params(context.intensity)
        return CostEstimate(
            time_sec=float(max(30, p.dd_size_mb // 2)),
            disk_write_mb=float(p.dd_size_mb),
            risks=["disk_write"],
            notes=["temp file only; no block device writes"],
        )

    def run(self, context: RunContext) -> ModuleResult:
        started = time.monotonic()
        p = get_params(context.intensity)
        warnings: List[str] = []
        temp = Path(context.work_dir) / f"lebench-dd-{os.getpid()}.bin"

        try:
            assert_safe_temp_file(temp)
        except PermissionError as exc:
            return ModuleResult.permission_denied(reason=str(exc), duration_sec=0.0)

        if is_blocked_write_path(temp):
            return ModuleResult.failed(reason="blocked_path", duration_sec=0.0)

        free = free_space_bytes(context.work_dir)
        need = int(p.dd_size_mb * 1.2 * 1024 * 1024)
        if free is not None and free < need:
            return ModuleResult.not_run(
                reason="insufficient_free_space",
                conditions={"free_bytes": free, "need_bytes": need},
                duration_sec=round(time.monotonic() - started, 3),
            )

        metrics: Dict[str, Any] = {
            "write_mbs": None,
            "read_mbs": None,
            "unit": "MB/s (10^6)",
        }
        conditions: Dict[str, Any] = {
            "filesize_mb": p.dd_size_mb,
            "bs": p.dd_bs,
            "path_kind": "regular_temp_file",
            "direct": p.dd_direct,
            "read_cache_note": "DD 读测试受页缓存影响，不可默认视为真实设备顺序读",
        }

        write_argv = [
            "dd",
            "if=/dev/zero",
            f"of={str(temp)}",
            f"bs={p.dd_bs}",
            f"count={p.dd_size_mb}",
            "conv=fdatasync",
            "status=progress",
        ]
        if p.dd_direct:
            write_argv.append("oflag=direct")

        # Write
        code_w, out_w, err_w = run_command(write_argv, timeout=600, max_stderr=64_000)
        text_w = (err_w or "") + "\n" + (out_w or "")
        write_mbs = _parse_dd_speed(text_w)
        if code_w != 0 and p.dd_direct:
            # Retry without direct (some FS/containers)
            warnings.append("dd_direct_write_failed_retry_without_direct")
            write_argv = [a for a in write_argv if a != "oflag=direct"]
            conditions["direct"] = False
            code_w, out_w, err_w = run_command(write_argv, timeout=600, max_stderr=64_000)
            text_w = (err_w or "") + "\n" + (out_w or "")
            write_mbs = _parse_dd_speed(text_w)

        metrics["write_mbs"] = write_mbs
        conditions["write_exit_code"] = code_w

        # Drop caches best-effort (root only); else warn — no shell
        dropped = False
        if context.environment.get("is_root") and Path("/proc/sys/vm/drop_caches").exists():
            run_command(["sync"], timeout=30)
            try:
                Path("/proc/sys/vm/drop_caches").write_text("3", encoding="utf-8")
                dropped = True
            except OSError:
                warnings.append("drop_caches_unavailable")
        else:
            warnings.append("read_may_be_cached_no_drop_caches")
        conditions["drop_caches"] = dropped

        read_argv = [
            "dd",
            f"if={str(temp)}",
            "of=/dev/null",
            f"bs={p.dd_bs}",
            "status=progress",
        ]
        if conditions["direct"]:
            read_argv.append("iflag=direct")

        code_r, out_r, err_r = run_command(read_argv, timeout=600, max_stderr=64_000)
        text_r = (err_r or "") + "\n" + (out_r or "")
        read_mbs = _parse_dd_speed(text_r)
        if code_r != 0 and conditions["direct"]:
            read_argv = [a for a in read_argv if a != "iflag=direct"]
            code_r, out_r, err_r = run_command(read_argv, timeout=600, max_stderr=64_000)
            text_r = (err_r or "") + "\n" + (out_r or "")
            read_mbs = _parse_dd_speed(text_r)
            warnings.append("dd_direct_read_failed_retry_without_direct")

        metrics["read_mbs"] = read_mbs
        conditions["read_exit_code"] = code_r

        # Cleanup
        try:
            if temp.exists():
                temp.unlink()
        except OSError as exc:
            warnings.append(f"temp_cleanup_failed:{exc}")

        duration = round(time.monotonic() - started, 3)
        tool = {"name": "dd", "version": tool_version("dd", ["--version"])}

        if write_mbs is None and read_mbs is None:
            return ModuleResult.failed(
                reason="dd_no_parseable_speed",
                metrics=metrics,
                conditions=conditions,
                warnings=warnings,
                tool=tool,
                duration_sec=duration,
            )

        status = (
            ModuleStatus.COMPLETED.value
            if write_mbs is not None and read_mbs is not None
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
