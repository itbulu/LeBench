"""Benchmark modules registry."""

from __future__ import annotations

from typing import Dict, List, Type

from lebench.modules.app_perf import AppPerfModule
from lebench.modules.base import BenchmarkModule
from lebench.modules.cloud_delivery import CloudDeliveryModule
from lebench.modules.compatibility import CompatibilityModule
from lebench.modules.cpu import CpuModule
from lebench.modules.disk_dd import DiskDdModule
from lebench.modules.disk_fio import DiskFioModule
from lebench.modules.gpu import GpuModule
from lebench.modules.ip_quality import IpQualityModule
from lebench.modules.memory import MemoryModule
from lebench.modules.network import NetworkModule
from lebench.modules.physical import PhysicalModule
from lebench.modules.ping import PingModule
from lebench.modules.routes import RoutesModule
from lebench.modules.stability import StabilityModule
from lebench.modules.system import SystemModule

_MODULE_CLASSES: List[Type[BenchmarkModule]] = [
    SystemModule,
    CpuModule,
    MemoryModule,
    DiskDdModule,
    DiskFioModule,
    NetworkModule,
    PingModule,
    RoutesModule,
    IpQualityModule,
    CompatibilityModule,
    StabilityModule,
    PhysicalModule,
    GpuModule,
    AppPerfModule,
    CloudDeliveryModule,
]


def build_registry() -> Dict[str, BenchmarkModule]:
    return {cls.name: cls() for cls in _MODULE_CLASSES}


def list_module_names() -> List[str]:
    return [cls.name for cls in _MODULE_CLASSES]


REGISTRY = build_registry()
