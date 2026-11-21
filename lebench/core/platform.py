"""Platform / OS / architecture / privilege detection."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass
class PlatformInfo:
    os_name: str
    os_release: str
    kernel: str
    arch: str
    python_version: str
    is_linux: bool
    is_root: bool
    euid: int
    hostname_redacted: str
    distro_id: Optional[str] = None
    distro_version: Optional[str] = None
    distro_pretty: Optional[str] = None
    container_hint: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def redact_hostname(hostname: str) -> str:
    if not hostname:
        return "<unknown>"
    if len(hostname) <= 2:
        return "*" * len(hostname)
    return hostname[0] + "*" * (len(hostname) - 2) + hostname[-1]


def _read_os_release() -> Dict[str, str]:
    path = Path("/etc/os-release")
    data: Dict[str, str] = {}
    if not path.is_file():
        return data
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return data
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value.strip().strip('"')
    return data


def _detect_container() -> Optional[str]:
    hints: List[str] = []
    if Path("/.dockerenv").exists():
        hints.append("dockerenv")
    cgroup = Path("/proc/1/cgroup")
    if cgroup.is_file():
        try:
            content = cgroup.read_text(encoding="utf-8", errors="replace").lower()
            for token in ("docker", "lxc", "kubepods", "containerd", "podman"):
                if token in content:
                    hints.append(token)
                    break
        except OSError:
            pass
    if Path("/run/.containerenv").exists():
        hints.append("podman")
    return ",".join(sorted(set(hints))) if hints else None


def detect_platform() -> PlatformInfo:
    warnings: List[str] = []
    uname = platform.uname()
    os_release = _read_os_release()
    try:
        hostname = platform.node() or ""
    except Exception:  # noqa: BLE001
        hostname = ""
        warnings.append("hostname_unavailable")

    arch = uname.machine or platform.machine() or "unknown"
    is_linux = uname.system.lower() == "linux"
    if not is_linux:
        warnings.append("non_linux_host")

    if arch not in {"x86_64", "amd64", "aarch64", "arm64"}:
        warnings.append(f"unverified_arch:{arch}")

    try:
        euid = os.geteuid()
    except AttributeError:
        euid = -1
        warnings.append("geteuid_unavailable")

    return PlatformInfo(
        os_name=uname.system,
        os_release=uname.release,
        kernel=uname.release,
        arch=arch,
        python_version=platform.python_version(),
        is_linux=is_linux,
        is_root=(euid == 0),
        euid=euid,
        hostname_redacted=redact_hostname(hostname),
        distro_id=os_release.get("ID"),
        distro_version=os_release.get("VERSION_ID"),
        distro_pretty=os_release.get("PRETTY_NAME"),
        container_hint=_detect_container(),
        warnings=warnings,
    )


def which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


def command_exists(cmd: str) -> bool:
    return which(cmd) is not None


def run_command(
    argv: Sequence[str],
    *,
    timeout: float = 30.0,
    max_stdout: int = 256_000,
    max_stderr: int = 64_000,
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[str] = None,
) -> Tuple[int, str, str]:
    """Run an external command with argv list only (no shell)."""
    if not argv:
        raise ValueError("argv must not be empty")
    if any(not isinstance(x, str) for x in argv):
        raise TypeError("argv items must be strings")

    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    try:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged_env,
            cwd=cwd,
            check=False,
        )
    except FileNotFoundError:
        return 127, "", f"command_not_found:{argv[0]}"
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        err = (exc.stderr or "") if isinstance(exc.stderr, str) else "timeout"
        return 124, out[:max_stdout], f"timeout:{timeout}s;{err[:max_stderr]}"
    except OSError as exc:
        return 126, "", f"os_error:{exc}"

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if len(stdout) > max_stdout:
        stdout = stdout[:max_stdout] + "\n...<truncated>"
    if len(stderr) > max_stderr:
        stderr = stderr[:max_stderr] + "\n...<truncated>"
    return completed.returncode, stdout, stderr


def free_space_bytes(path: str | Path) -> Optional[int]:
    try:
        usage = shutil.disk_usage(str(path))
        return int(usage.free)
    except OSError:
        return None
