"""Unified benchmark module interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from lebench.core.result import ModuleResult
from lebench.core.safety import CostEstimate, SafetyPolicy


@dataclass
class ProbeResult:
    available: bool
    reason: Optional[str] = None
    dependencies: Dict[str, bool] = field(default_factory=dict)
    privileges: Dict[str, bool] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "reason": self.reason,
            "dependencies": dict(self.dependencies),
            "privileges": dict(self.privileges),
            "details": dict(self.details),
        }


@dataclass
class RunContext:
    product_type: str
    intensity: str
    work_dir: str
    output_dir: str
    yes: bool = False
    dry_run: bool = False
    allow_sensitive: bool = False
    safety: SafetyPolicy = field(default_factory=SafetyPolicy)
    environment: Dict[str, Any] = field(default_factory=dict)
    cancel_requested: bool = False


class BenchmarkModule(ABC):
    name: str = "base"
    description: str = ""
    stage: str = "unknown"  # s0 / s1 / s2 / s3 / s4
    implemented: bool = False
    dependencies: List[str] = []
    optional_dependencies: List[str] = []

    @abstractmethod
    def probe(self, context: RunContext) -> ProbeResult:
        raise NotImplementedError

    def estimate_cost(self, context: RunContext) -> CostEstimate:
        return CostEstimate(time_sec=1.0, notes=[f"module:{self.name}"])

    @abstractmethod
    def run(self, context: RunContext) -> ModuleResult:
        raise NotImplementedError
