"""Internal snapshot writer — NOT the website import protocol."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from lebench.core.result import RunResult
from lebench.core.safety import redact_mapping


NOTICE = (
    "This file uses lebench-internal-v0. "
    "It is NOT the Lezaiyun / website import schema. "
    "Do not upload this snapshot as site Schema v1.0."
)


def build_snapshot(result: RunResult, *, allow_sensitive: bool = False) -> Dict[str, Any]:
    data = result.to_dict()
    data["notice"] = NOTICE
    if not allow_sensitive:
        data = redact_mapping(data, allow_sensitive=False)
        data["notice"] = NOTICE
        data["privacy"] = {**(data.get("privacy") or {}), "redacted": True}
    return data


def write_internal_json(
    result: RunResult,
    path: str | Path,
    *,
    allow_sensitive: bool = False,
) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = build_snapshot(result, allow_sensitive=allow_sensitive)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out
