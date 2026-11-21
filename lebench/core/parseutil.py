"""Small parsing helpers for tool output."""

from __future__ import annotations

import re
from typing import Optional


def first_float(pattern: str, text: str, flags: int = re.I | re.M) -> Optional[float]:
    m = re.search(pattern, text, flags)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def first_int(pattern: str, text: str, flags: int = re.I | re.M) -> Optional[int]:
    v = first_float(pattern, text, flags)
    return int(v) if v is not None else None


def first_str(pattern: str, text: str, flags: int = re.I | re.M) -> Optional[str]:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def tool_version(argv0: str, version_args: Optional[list] = None) -> Optional[str]:
    from lebench.core.platform import run_command

    args = version_args or ["--version"]
    code, out, err = run_command([argv0, *args], timeout=8)
    text = (out or "") + "\n" + (err or "")
    if code not in (0, 1) and not text.strip():
        return None
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", text)
    return m.group(1) if m else text.strip().splitlines()[0][:80] if text.strip() else None
