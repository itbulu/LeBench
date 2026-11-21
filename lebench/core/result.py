"""Unified internal result model (lebench-internal-v0)."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


INTERNAL_FORMAT = "lebench-internal-v0"
TOOL_NAME = "LeBench"


class ModuleStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_RUN = "not_run"
    NOT_APPLICABLE = "not_applicable"
    PERMISSION_DENIED = "permission_denied"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def new_run_id() -> str:
    return str(uuid.uuid4())


@dataclass
class ModuleResult:
    status: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    tool: Dict[str, Any] = field(default_factory=dict)
    conditions: Dict[str, Any] = field(default_factory=dict)
    duration_sec: Optional[float] = None
    reason: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    raw_refs: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Drop empty optional noise for cleaner snapshots
        if not data.get("reason"):
            data.pop("reason", None)
        if not data.get("warnings"):
            data.pop("warnings", None)
        if not data.get("errors"):
            data.pop("errors", None)
        if not data.get("raw_refs"):
            data.pop("raw_refs", None)
        if not data.get("sources"):
            data.pop("sources", None)
        if data.get("duration_sec") is None:
            data.pop("duration_sec", None)
        return data

    @classmethod
    def not_run(cls, reason: str, **kwargs: Any) -> "ModuleResult":
        return cls(status=ModuleStatus.NOT_RUN.value, reason=reason, **kwargs)

    @classmethod
    def not_applicable(cls, reason: str, **kwargs: Any) -> "ModuleResult":
        return cls(status=ModuleStatus.NOT_APPLICABLE.value, reason=reason, **kwargs)

    @classmethod
    def permission_denied(cls, reason: str, **kwargs: Any) -> "ModuleResult":
        return cls(status=ModuleStatus.PERMISSION_DENIED.value, reason=reason, **kwargs)

    @classmethod
    def failed(cls, reason: str, errors: Optional[List[str]] = None, **kwargs: Any) -> "ModuleResult":
        return cls(
            status=ModuleStatus.FAILED.value,
            reason=reason,
            errors=errors or ([reason] if reason else []),
            **kwargs,
        )


@dataclass
class RunResult:
    product_type: str
    intensity: str
    modules: Dict[str, ModuleResult] = field(default_factory=dict)
    run_id: str = field(default_factory=new_run_id)
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: Optional[str] = None
    tool_version: str = "0.2.0"
    warnings: List[str] = field(default_factory=list)
    environment: Dict[str, Any] = field(default_factory=dict)
    selected_modules: List[str] = field(default_factory=list)
    skipped_modules: List[str] = field(default_factory=list)
    dry_run: bool = False
    privacy: Dict[str, Any] = field(default_factory=dict)

    def finish(self) -> None:
        self.finished_at = utc_now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "internal_format": INTERNAL_FORMAT,
            "run_id": self.run_id,
            "product_type": self.product_type,
            "intensity": self.intensity,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "tool": {"name": TOOL_NAME, "version": self.tool_version},
            "dry_run": self.dry_run,
            "selected_modules": list(self.selected_modules),
            "skipped_modules": list(self.skipped_modules),
            "environment": dict(self.environment),
            "privacy": dict(self.privacy),
            "warnings": list(self.warnings),
            "modules": {name: result.to_dict() for name, result in self.modules.items()},
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent) + "\n"
