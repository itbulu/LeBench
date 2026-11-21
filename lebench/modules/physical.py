"""Read-only physical hardware probes (lscpu/numactl/dmidecode/smartctl/mdadm)."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from lebench.core.parseutil import first_int, first_str
from lebench.core.platform import command_exists, run_command
from lebench.core.result import ModuleResult, ModuleStatus
from lebench.core.safety import CostEstimate
from lebench.modules.base import BenchmarkModule, ProbeResult, RunContext


def _run(argv: List[str], timeout: float = 20.0):
    return run_command(argv, timeout=timeout)


class PhysicalModule(BenchmarkModule):
    name = "physical"
    description = "物理硬件只读探测（禁止修改 RAID/SMART 设置）"
    stage = "s4"
    implemented = True
    dependencies: List[str] = []
    optional_dependencies = ["lscpu", "numactl", "dmidecode", "smartctl", "mdadm"]

    def probe(self, context: RunContext) -> ProbeResult:
        deps = {d: command_exists(d) for d in self.optional_dependencies}
        return ProbeResult(
            available=True,
            dependencies=deps,
            privileges={"root": bool(context.environment.get("is_root"))},
            details={"read_only": True},
        )

    def estimate_cost(self, context: RunContext) -> CostEstimate:
        return CostEstimate(time_sec=10.0, notes=["read-only hardware probes"])

    def run(self, context: RunContext) -> ModuleResult:
        started = time.monotonic()
        warnings: List[str] = []
        metrics: Dict[str, Any] = {}
        sources: List[str] = []
        denied: List[str] = []

        # lscpu
        if command_exists("lscpu"):
            code, out, err = _run(["lscpu"])
            sources.append("lscpu")
            if code == 0:
                metrics["cpu_model"] = first_str(r"^Model name:\s*(.+)$", out or "", re.M)
                metrics["cpu_sockets"] = first_int(r"^Socket\(s\):\s*(\d+)", out or "", re.M)
                metrics["cpu_cores_per_socket"] = first_int(r"^Core\(s\) per socket:\s*(\d+)", out or "", re.M)
                metrics["cpu_threads"] = first_int(r"^CPU\(s\):\s*(\d+)", out or "", re.M)
                metrics["numa_nodes_lscpu"] = first_int(r"^NUMA node\(s\):\s*(\d+)", out or "", re.M)
            else:
                warnings.append(f"lscpu_failed:{err[:80] if err else code}")

        # numactl
        if command_exists("numactl"):
            code, out, err = _run(["numactl", "--hardware"])
            sources.append("numactl")
            if code == 0:
                metrics["numa_nodes"] = first_int(r"available:\s*(\d+)\s*nodes", out or "")
            elif "permission" in (err or "").lower():
                denied.append("numactl")
            else:
                warnings.append("numactl_failed")

        # dmidecode (often needs root)
        if command_exists("dmidecode"):
            sources.append("dmidecode")
            code, out, err = _run(["dmidecode", "-t", "memory"])
            if code == 0 and out:
                ecc = None
                if re.search(r"Error Correction Type:\s*Multi-bit ECC", out, re.I):
                    ecc = "multi-bit"
                elif re.search(r"Error Correction Type:\s*Single-bit ECC", out, re.I):
                    ecc = "single-bit"
                elif re.search(r"Error Correction Type:\s*None", out, re.I):
                    ecc = "none"
                metrics["ecc"] = ecc
                dimms = re.findall(r"^Size:\s*(.+)$", out, re.M)
                metrics["dimm_count"] = len([d for d in dimms if "No Module" not in d and "Not Installed" not in d])
                metrics["dimm_sizes"] = [d.strip() for d in dimms if "No Module" not in d][:32]
            else:
                if code != 0:
                    denied.append("dmidecode")
                    metrics["ecc"] = None
                    warnings.append("dmidecode_permission_or_failed")

        # smartctl — read-only scan
        if command_exists("smartctl"):
            sources.append("smartctl")
            code, out, err = _run(["smartctl", "--scan"])
            if code == 0:
                devices = []
                for line in (out or "").splitlines():
                    parts = line.split("#")[0].strip().split()
                    if parts:
                        devices.append(parts[0])
                smart_rows = []
                for dev in devices[:8]:
                    # -i / -H only — never -s on/off
                    c2, o2, e2 = _run(["smartctl", "-H", "-i", dev], timeout=30)
                    if c2 in (0, 4):  # 4 often means some attrs unavailable
                        health = first_str(r"SMART overall-health.*:\s*(.+)$", o2 or "", re.M)
                        model = first_str(r"Device Model:\s*(.+)$", o2 or "", re.M) or first_str(
                            r"Model Number:\s*(.+)$", o2 or "", re.M
                        )
                        smart_rows.append(
                            {
                                "device": dev if context.allow_sensitive else "<disk>",
                                "health": health,
                                "model": model,
                            }
                        )
                    else:
                        if "permission" in (e2 or "").lower() or c2 == 2:
                            denied.append(f"smartctl:{dev}")
                metrics["smart"] = smart_rows
            else:
                denied.append("smartctl")
                warnings.append("smartctl_scan_failed")

        # mdadm assemble? NO — only --detail --scan read
        if command_exists("mdadm"):
            sources.append("mdadm")
            code, out, err = _run(["mdadm", "--detail", "--scan"])
            if code == 0:
                metrics["raid_arrays"] = [
                    line.strip() for line in (out or "").splitlines() if line.strip()
                ]
            else:
                if "permission" in (err or "").lower():
                    denied.append("mdadm")
                metrics["raid_arrays"] = []

        conditions = {
            "read_only": True,
            "modified_raid_or_smart": False,
            "permission_denied_tools": denied,
            "note": "不等于 IPMI/KVM/救援等产品能力",
        }
        duration = round(time.monotonic() - started, 3)

        if denied and not any(metrics.get(k) for k in ("cpu_model", "numa_nodes", "smart", "raid_arrays", "ecc")):
            return ModuleResult.permission_denied(
                reason="physical_probes_permission_denied",
                metrics=metrics,
                conditions=conditions,
                warnings=warnings,
                sources=sources,
                duration_sec=duration,
                tool={"name": "lebench.physical", "version": "0.1.0"},
            )

        status = ModuleStatus.COMPLETED.value
        if denied:
            status = ModuleStatus.PARTIAL.value
            warnings.append("some_tools_permission_denied")

        return ModuleResult(
            status=status,
            metrics=metrics,
            conditions=conditions,
            warnings=warnings,
            sources=sources,
            tool={"name": "lebench.physical", "version": "0.1.0"},
            duration_sec=duration,
        )
