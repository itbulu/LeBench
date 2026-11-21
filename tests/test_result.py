from __future__ import annotations

import json

from lebench.core.result import INTERNAL_FORMAT, ModuleResult, RunResult


def test_module_status_helpers():
    assert ModuleResult.not_run("x").status == "not_run"
    assert ModuleResult.failed("boom").status == "failed"
    assert ModuleResult.permission_denied("need root").status == "permission_denied"


def test_run_result_internal_format():
    run = RunResult(product_type="vps", intensity="quick")
    run.modules["system"] = ModuleResult(
        status="completed",
        metrics={"cpu_cores": 2},
        duration_sec=0.1,
    )
    run.finish()
    data = run.to_dict()
    assert data["internal_format"] == INTERNAL_FORMAT
    assert data["product_type"] == "vps"
    assert data["modules"]["system"]["status"] == "completed"
    assert data["finished_at"]
    # JSON serializable
    json.loads(run.to_json())
