"""System information collection module (S0 P0)."""

from __future__ import annotations

import os
import platform
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lebench.core.platform import command_exists, detect_platform, run_command
from lebench.core.result import ModuleResult, ModuleStatus
from lebench.core.safety import CostEstimate
from lebench.modules.base import BenchmarkModule, ProbeResult, RunContext


def _read_text(path: str | Path) -> Optional[str]:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _first_match(pattern: str, text: str, flags: int = re.I) -> Optional[str]:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _parse_meminfo() -> Dict[str, int]:
    raw = _read_text("/proc/meminfo") or ""
    result: Dict[str, int] = {}
    for key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
        m = re.search(rf"^{key}:\s+(\d+)\s+kB", raw, re.M)
        if m:
            result[key] = int(m.group(1))
    return result


def _cpu_model_and_cores() -> Tuple[Optional[str], Optional[int], Optional[float], List[str]]:
    sources: List[str] = []
    model: Optional[str] = None
    cores: Optional[int] = None
    freq_mhz: Optional[float] = None

    cpuinfo = _read_text("/proc/cpuinfo")
    if cpuinfo:
        sources.append("/proc/cpuinfo")
        model = _first_match(r"^model name\s*:\s*(.+)$", cpuinfo)
        if not model:
            model = _first_match(r"^Hardware\s*:\s*(.+)$", cpuinfo)
        siblings = re.findall(r"^processor\s*:\s*\d+", cpuinfo, re.M)
        if siblings:
            cores = len(siblings)
        mhz = _first_match(r"^cpu MHz\s*:\s*([0-9.]+)", cpuinfo)
        if mhz:
            try:
                freq_mhz = float(mhz)
            except ValueError:
                pass

    if command_exists("lscpu"):
        code, out, _ = run_command(["lscpu"], timeout=10)
        if code == 0 and out:
            sources.append("lscpu")
            model = model or _first_match(r"^Model name:\s*(.+)$", out, re.M)
            if cores is None:
                c = _first_match(r"^CPU\(s\):\s*(\d+)", out, re.M)
                if c:
                    cores = int(c)
            if freq_mhz is None:
                for pat in (
                    r"^CPU max MHz:\s*([0-9.]+)",
                    r"^CPU MHz:\s*([0-9.]+)",
                ):
                    f = _first_match(pat, out, re.M)
                    if f:
                        try:
                            freq_mhz = float(f)
                            break
                        except ValueError:
                            pass

    if cores is None:
        try:
            cores = os.cpu_count()
            sources.append("os.cpu_count")
        except Exception:  # noqa: BLE001
            pass

    return model, cores, freq_mhz, sources


def _storage_summary() -> Tuple[Optional[float], Optional[str], List[str], List[str]]:
    """Return total_gb, type_guess, mount notes, sources."""
    sources: List[str] = []
    warnings: List[str] = []
    total_bytes = 0
    types: List[str] = []

    # Prefer lsblk if available (read-only)
    if command_exists("lsblk"):
        code, out, err = run_command(
            ["lsblk", "-b", "-d", "-n", "-o", "NAME,SIZE,TYPE,ROTA,TRAN,MODEL"],
            timeout=10,
        )
        if code == 0 and out:
            sources.append("lsblk")
            for line in out.splitlines():
                parts = line.split()
                if len(parts) < 3:
                    continue
                # NAME SIZE TYPE ...
                try:
                    size = int(parts[1])
                except ValueError:
                    continue
                dtype = parts[2]
                if dtype != "disk":
                    continue
                total_bytes += size
                rota = None
                tran = None
                # After TYPE: ROTA TRAN MODEL...
                rest = parts[3:]
                if rest:
                    try:
                        rota = int(rest[0])
                    except ValueError:
                        rota = None
                    if len(rest) > 1:
                        tran = rest[1]
                if tran and tran.lower() in {"nvme", "sata", "sas", "usb"}:
                    types.append(tran.lower())
                elif rota == 0:
                    types.append("ssd")
                elif rota == 1:
                    types.append("hdd")
        elif err:
            warnings.append(f"lsblk_error:{err.strip()[:120]}")

    if total_bytes <= 0:
        # Fallback: sum filesystem sizes via df (visible capacity, may be quota)
        code, out, _ = run_command(["df", "-B1", "--output=source,size,fstype,target"], timeout=10)
        if code == 0 and out:
            sources.append("df")
            warnings.append("storage_from_df_may_reflect_quota_or_bind_mounts")
            seen = set()
            for line in out.splitlines()[1:]:
                parts = line.split()
                if len(parts) < 4:
                    continue
                source, size_s, fstype, target = parts[0], parts[1], parts[2], parts[3]
                if source in seen:
                    continue
                if not source.startswith("/dev/") and source not in {"overlay", "tmpfs"}:
                    # skip pseudo
                    if fstype in {"tmpfs", "devtmpfs", "proc", "sysfs", "cgroup", "cgroup2"}:
                        continue
                if fstype in {"tmpfs", "devtmpfs", "proc", "sysfs", "cgroup", "cgroup2", "overlay"}:
                    continue
                try:
                    size = int(size_s)
                except ValueError:
                    continue
                seen.add(source)
                total_bytes += size
                types.append(fstype)

    total_gb = round(total_bytes / (1024**3), 2) if total_bytes > 0 else None
    type_guess = None
    if types:
        # Prefer nvme/ssd labels
        lowered = [t.lower() for t in types]
        for prefer in ("nvme", "ssd", "hdd", "sata"):
            if prefer in lowered:
                type_guess = prefer
                break
        if type_guess is None:
            type_guess = ",".join(sorted(set(lowered))[:3])
    return total_gb, type_guess, warnings, sources


def _virtualization() -> Tuple[Optional[str], List[str]]:
    sources: List[str] = []
    if command_exists("systemd-detect-virt"):
        code, out, _ = run_command(["systemd-detect-virt"], timeout=5)
        sources.append("systemd-detect-virt")
        if code == 0:
            virt = (out or "").strip()
            if virt and virt != "none":
                return virt, sources
            return "none", sources
        if code == 1 and (out or "").strip() == "none":
            return "none", sources

    # Fallbacks
    dmi = _read_text("/sys/class/dmi/id/product_name") or ""
    if dmi:
        sources.append("/sys/class/dmi/id/product_name")
        dmi_l = dmi.strip().lower()
        for token in ("kvm", "qemu", "vmware", "virtualbox", "xen", "bochs", "hyper-v", "openstack"):
            if token in dmi_l:
                return token, sources

    cpuinfo = _read_text("/proc/cpuinfo") or ""
    if "hypervisor" in cpuinfo.lower():
        sources.append("/proc/cpuinfo:flags")
        return "hypervisor", sources

    return None, sources


def _bbr_congestion() -> Tuple[Optional[str], Optional[bool], List[str]]:
    sources: List[str] = []
    cc = _read_text("/proc/sys/net/ipv4/tcp_congestion_control")
    if cc:
        sources.append("/proc/sys/net/ipv4/tcp_congestion_control")
        cc = cc.strip()
    avail = _read_text("/proc/sys/net/ipv4/tcp_available_congestion_control")
    bbr = None
    if avail:
        sources.append("/proc/sys/net/ipv4/tcp_available_congestion_control")
        bbr = "bbr" in avail.lower()
    if cc and bbr is None:
        bbr = cc.lower() == "bbr"
    return cc, bbr, sources


def _ipv46_available() -> Tuple[Optional[bool], Optional[bool], List[str], List[str]]:
    sources: List[str] = []
    warnings: List[str] = []
    ipv4 = None
    ipv6 = None

    # Local stack presence via /proc
    if Path("/proc/net/fib_trie").exists() or Path("/proc/net/route").exists():
        sources.append("/proc/net/route")
        ipv4 = True
    if Path("/proc/net/if_inet6").exists():
        sources.append("/proc/net/if_inet6")
        content = _read_text("/proc/net/if_inet6") or ""
        # Non-empty usually means IPv6 addresses configured (may include link-local only)
        ipv6 = bool(content.strip())
        if ipv6 and all(line.split()[0].startswith("fe80") for line in content.splitlines() if line.strip()):
            warnings.append("ipv6_link_local_only")

    # Optional: ip command for confirmation without revealing public addresses in metrics
    if command_exists("ip"):
        code, out, _ = run_command(["ip", "-o", "addr", "show", "scope", "global"], timeout=5)
        if code == 0:
            sources.append("ip_addr_scope_global")
            has_v4 = bool(re.search(r"\binet\s+", out or ""))
            has_v6 = bool(re.search(r"\binet6\s+", out or ""))
            if has_v4:
                ipv4 = True
            if has_v6:
                ipv6 = True
            if not has_v4 and ipv4 is None:
                ipv4 = False
            if not has_v6 and ipv6 is None:
                ipv6 = False

    return ipv4, ipv6, warnings, sources


class SystemModule(BenchmarkModule):
    name = "system"
    description = "采集 CPU/内存/存储/虚拟化/OS/网络基础信息"
    stage = "s0"
    implemented = True
    dependencies: List[str] = []
    optional_dependencies = ["lscpu", "lsblk", "systemd-detect-virt", "ip", "df"]

    def probe(self, context: RunContext) -> ProbeResult:
        deps = {d: command_exists(d) for d in self.optional_dependencies}
        return ProbeResult(
            available=True,
            reason=None,
            dependencies=deps,
            privileges={"root": bool(context.environment.get("is_root"))},
            details={"reads": ["/proc", "/sys", "/etc/os-release"]},
        )

    def estimate_cost(self, context: RunContext) -> CostEstimate:
        return CostEstimate(
            time_sec=2.0,
            disk_write_mb=0.0,
            network_mb=0.0,
            cpu_heavy=False,
            notes=["read-only system probe"],
        )

    def run(self, context: RunContext) -> ModuleResult:
        started = time.monotonic()
        warnings: List[str] = []
        sources: List[str] = []

        plat = detect_platform()
        warnings.extend(plat.warnings)

        model, cores, freq_mhz, cpu_sources = _cpu_model_and_cores()
        sources.extend(cpu_sources)

        mem = _parse_meminfo()
        if mem:
            sources.append("/proc/meminfo")

        storage_gb, storage_type, storage_warns, storage_sources = _storage_summary()
        warnings.extend(storage_warns)
        sources.extend(storage_sources)

        virt, virt_sources = _virtualization()
        sources.extend(virt_sources)
        if plat.container_hint:
            warnings.append(f"container_hint:{plat.container_hint}")
            sources.append("container_detection")

        cc, bbr, bbr_sources = _bbr_congestion()
        sources.extend(bbr_sources)

        ipv4, ipv6, ip_warns, ip_sources = _ipv46_available()
        warnings.extend(ip_warns)
        sources.extend(ip_sources)

        os_label = plat.distro_pretty or f"{plat.os_name} {plat.os_release}"
        metrics: Dict[str, Any] = {
            "cpu_model": model,
            "arch": plat.arch,
            "cpu_cores": cores,
            "cpu_freq_mhz": freq_mhz,
            "memory_total_mb": round(mem["MemTotal"] / 1024, 2) if "MemTotal" in mem else None,
            "memory_available_mb": round(mem["MemAvailable"] / 1024, 2) if "MemAvailable" in mem else None,
            "swap_total_mb": round(mem["SwapTotal"] / 1024, 2) if "SwapTotal" in mem else None,
            "storage_total_gb": storage_gb,
            "storage_type": storage_type,
            "virtualization": virt,
            "os": os_label,
            "kernel": plat.kernel,
            "bbr": bbr,
            "tcp_congestion_control": cc,
            "ipv4": ipv4,
            "ipv6": ipv6,
        }

        # Visibility limits note
        conditions = {
            "collection": "guest_visible_only",
            "note": "容器/虚拟机内采集结果反映可见资源，不等于宿主机或商家广告配置",
            "distro_id": plat.distro_id,
            "distro_version": plat.distro_version,
            "python_version": platform.python_version(),
            "is_root": plat.is_root,
            "container_hint": plat.container_hint,
        }

        missing = [k for k, v in metrics.items() if v is None and k in {
            "cpu_model", "arch", "cpu_cores", "memory_total_mb", "os", "kernel"
        }]
        status = ModuleStatus.COMPLETED.value
        reason = None
        if missing:
            status = ModuleStatus.PARTIAL.value
            reason = f"missing_fields:{','.join(missing)}"
            warnings.append(reason)

        duration = round(time.monotonic() - started, 3)
        return ModuleResult(
            status=status,
            metrics=metrics,
            tool={"name": "lebench.system", "version": "0.1.0"},
            conditions=conditions,
            duration_sec=duration,
            reason=reason,
            warnings=warnings,
            sources=sorted(set(sources)),
        )
