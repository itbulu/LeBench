from __future__ import annotations

import sys

import pytest

from lebench.modules.base import RunContext
from lebench.modules.system import SystemModule


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="system module targets Linux")
def test_system_module_runs_on_linux(tmp_path):
    mod = SystemModule()
    ctx = RunContext(
        product_type="vps",
        intensity="quick",
        work_dir=str(tmp_path),
        output_dir=str(tmp_path),
        environment={"is_root": False, "arch": "x86_64"},
    )
    probe = mod.probe(ctx)
    assert probe.available is True
    result = mod.run(ctx)
    assert result.status in {"completed", "partial"}
    assert "arch" in result.metrics
    assert "os" in result.metrics
    assert "kernel" in result.metrics
    assert result.metrics.get("cpu_cores") is not None or result.status == "partial"


def test_system_probe_always_available(tmp_path):
    mod = SystemModule()
    ctx = RunContext(
        product_type="vps",
        intensity="quick",
        work_dir=str(tmp_path),
        output_dir=str(tmp_path),
        environment={},
    )
    assert mod.probe(ctx).available is True
    assert mod.implemented is True
