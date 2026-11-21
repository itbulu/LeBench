"""Safety budgets, path checks, confirmation helpers, privacy redaction."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set


BLOCKED_WRITE_PREFIXES = (
    "/dev/",
    "/proc/",
    "/sys/",
    "/boot/",
    "/etc/",
)

SENSITIVE_KEYS = {
    "public_ip",
    "public_ipv4",
    "public_ipv6",
    "hostname",
    "serial",
    "serial_number",
    "mac",
    "mac_address",
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "private_key",
}

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
MAC_RE = re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b")


@dataclass
class CostEstimate:
    time_sec: float = 0.0
    disk_write_mb: float = 0.0
    network_mb: float = 0.0
    cpu_heavy: bool = False
    risks: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def merge(self, other: "CostEstimate") -> "CostEstimate":
        return CostEstimate(
            time_sec=self.time_sec + other.time_sec,
            disk_write_mb=self.disk_write_mb + other.disk_write_mb,
            network_mb=self.network_mb + other.network_mb,
            cpu_heavy=self.cpu_heavy or other.cpu_heavy,
            risks=list(dict.fromkeys(self.risks + other.risks)),
            notes=list(dict.fromkeys(self.notes + other.notes)),
        )


@dataclass
class SafetyPolicy:
    max_disk_write_mb: float = 2048.0
    max_network_mb: float = 512.0
    max_runtime_sec: float = 3600.0
    allow_sensitive_export: bool = False
    require_confirm_high_risk: bool = True
    work_dir: Optional[str] = None


def is_blocked_write_path(path: str | Path) -> bool:
    resolved = str(Path(path).resolve()) if Path(path).exists() else str(Path(path))
    normalized = resolved.replace("\\", "/")
    lower = normalized.lower()
    for prefix in BLOCKED_WRITE_PREFIXES:
        if lower.startswith(prefix.rstrip("/")) or f"/{prefix.strip('/')}/" in f"/{lower}/":
            # Direct block-device style paths
            pass
    # Explicit block device patterns
    name = Path(normalized).name
    if re.match(r"^(sd[a-z]+|nvme\d+n\d+|vd[a-z]+|xvd[a-z]+|hd[a-z]+|mmcblk\d+)$", name):
        return True
    if lower.startswith("/dev/"):
        return True
    if lower.startswith("/proc/") or lower.startswith("/sys/"):
        return True
    return False


def assert_safe_temp_file(path: str | Path) -> Path:
    p = Path(path)
    if is_blocked_write_path(p):
        raise PermissionError(f"refusing_write_to_blocked_path:{p}")
    # Must be a regular file path under a writable directory, never a device
    parent = p.parent
    if parent.exists() and not parent.is_dir():
        raise PermissionError(f"parent_not_directory:{parent}")
    return p


def _key_is_sensitive(key: str) -> bool:
    key_l = key.lower()
    # Already-redacted fields (e.g. hostname_redacted) must not be wiped again
    if key_l.endswith("_redacted"):
        return False
    return key_l in SENSITIVE_KEYS or any(
        key_l.endswith(f"_{s}") or key_l.startswith(f"{s}_") for s in SENSITIVE_KEYS
    )


def redact_value(key: str, value: Any, *, allow_sensitive: bool = False) -> Any:
    if allow_sensitive:
        return value
    if _key_is_sensitive(key):
        return "<redacted>"
    if isinstance(value, str):
        text = IPV4_RE.sub("<ip>", value)
        text = MAC_RE.sub("<mac>", text)
        return text
    if isinstance(value, dict):
        return {k: redact_value(k, v, allow_sensitive=allow_sensitive) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(key, v, allow_sensitive=allow_sensitive) for v in value]
    return value


def redact_mapping(data: Dict[str, Any], *, allow_sensitive: bool = False) -> Dict[str, Any]:
    return {k: redact_value(k, v, allow_sensitive=allow_sensitive) for k, v in data.items()}


def confirm(prompt: str, *, assumed_yes: bool = False, high_risk: bool = False) -> bool:
    if assumed_yes and not high_risk:
        return True
    if assumed_yes and high_risk:
        # --yes must not bypass destructive / high-risk bans
        return False
    try:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


def summarize_risks(estimates: Iterable[CostEstimate]) -> List[str]:
    risks: List[str] = []
    seen: Set[str] = set()
    for est in estimates:
        for r in est.risks:
            if r not in seen:
                seen.add(r)
                risks.append(r)
    return risks
