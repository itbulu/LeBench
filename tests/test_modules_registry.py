from __future__ import annotations

from lebench.modules import REGISTRY, list_module_names


def test_all_expected_modules_registered():
    names = set(list_module_names())
    expected = {
        "system",
        "cpu",
        "memory",
        "disk_dd",
        "disk_fio",
        "network",
        "ping",
        "routes",
        "ip_quality",
        "compatibility",
        "stability",
        "physical",
        "gpu",
        "app_perf",
        "cloud_delivery",
    }
    assert names == expected
    for name, mod in REGISTRY.items():
        assert mod.implemented is True
        assert mod.name == name


def test_cloud_delivery_records_not_run_features(tmp_path):
    from lebench.modules.base import RunContext
    from lebench.modules.cloud_delivery import CloudDeliveryModule

    ctx = RunContext(
        product_type="bare_metal",
        intensity="standard",
        work_dir=str(tmp_path),
        output_dir=str(tmp_path),
    )
    result = CloudDeliveryModule().run(ctx)
    assert result.status == "completed"
    assert result.metrics["features"]["create_instance"]["status"] == "not_run"


def test_app_perf_requires_enable(tmp_path):
    from lebench.modules.app_perf import AppPerfModule
    from lebench.modules.base import RunContext

    ctx = RunContext(
        product_type="lightweight",
        intensity="standard",
        work_dir=str(tmp_path),
        output_dir=str(tmp_path),
        environment={},
    )
    result = AppPerfModule().run(ctx)
    assert result.status == "not_run"


def test_app_perf_runs_when_enabled(tmp_path):
    from lebench.modules.app_perf import AppPerfModule
    from lebench.modules.base import RunContext

    ctx = RunContext(
        product_type="lightweight",
        intensity="quick",
        work_dir=str(tmp_path),
        output_dir=str(tmp_path),
        environment={"enable_app_perf": True},
    )
    result = AppPerfModule().run(ctx)
    assert result.status in {"completed", "partial"}
    assert result.metrics.get("requests") == 64


def test_config_loader_example_yaml():
    from pathlib import Path

    from lebench.core.config_loader import load_config

    path = Path(__file__).resolve().parents[1] / "lebench" / "data" / "ping_targets.example.yaml"
    data = load_config(path)
    assert isinstance(data.get("targets"), list)
    assert data["targets"][0]["host"] == "1.1.1.1"
