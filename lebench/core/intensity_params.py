"""Tunable intensity parameters (recorded in reports; not frozen claims)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class IntensityParams:
    # CPU (sysbench)
    cpu_threads: int = 0  # 0 = auto (cpu_count)
    cpu_max_prime: int = 20000
    cpu_time_sec: int = 10

    # Memory (sysbench)
    memory_threads: int = 1
    memory_block_size: str = "1M"
    memory_total_size: str = "1G"

    # Disk DD
    dd_size_mb: int = 256
    dd_bs: str = "1M"
    dd_direct: bool = True

    # Disk FIO
    fio_filesize: str = "256M"
    fio_runtime_sec: int = 15
    fio_iodepth: int = 32
    fio_numjobs: int = 1
    fio_ioengine: str = "libaio"

    # Network
    network_max_mb_per_node: float = 50.0
    network_max_total_mb: float = 200.0
    network_timeout_sec: float = 60.0

    # Ping
    ping_samples: int = 10
    ping_timeout_sec: float = 2.0

    # Routes
    routes_max_hops: int = 20
    routes_timeout_sec: float = 60.0

    # Stability
    stability_duration_sec: int = 60
    stability_interval_sec: float = 2.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


PARAMS_BY_INTENSITY: Dict[str, IntensityParams] = {
    "quick": IntensityParams(
        cpu_time_sec=5,
        cpu_max_prime=10000,
        memory_total_size="256M",
        dd_size_mb=64,
        fio_filesize="64M",
        fio_runtime_sec=5,
        fio_iodepth=8,
        network_max_mb_per_node=10.0,
        network_max_total_mb=30.0,
        ping_samples=4,
        stability_duration_sec=20,
    ),
    "standard": IntensityParams(
        cpu_time_sec=15,
        memory_total_size="1G",
        dd_size_mb=512,
        fio_filesize="512M",
        fio_runtime_sec=20,
        network_max_mb_per_node=50.0,
        network_max_total_mb=200.0,
        ping_samples=10,
        stability_duration_sec=60,
    ),
    "deep": IntensityParams(
        cpu_time_sec=30,
        cpu_max_prime=20000,
        memory_total_size="2G",
        dd_size_mb=1024,
        fio_filesize="1G",
        fio_runtime_sec=40,
        fio_iodepth=64,
        network_max_mb_per_node=100.0,
        network_max_total_mb=500.0,
        ping_samples=20,
        stability_duration_sec=180,
        routes_max_hops=30,
    ),
}


def get_params(intensity: str) -> IntensityParams:
    return PARAMS_BY_INTENSITY.get(intensity, PARAMS_BY_INTENSITY["standard"])
