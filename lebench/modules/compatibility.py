"""Optional streaming/AI endpoint reachability — never claim full unlock from HTTP 200."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lebench.core.config_loader import find_config, load_config
from lebench.core.result import ModuleResult, ModuleStatus
from lebench.core.safety import CostEstimate
from lebench.modules.base import BenchmarkModule, ProbeResult, RunContext

DEFAULT_CHECKS = [
    {"name": "cloudflare", "url": "https://1.1.1.1", "category": "network"},
    {"name": "openai_api_reachable", "url": "https://api.openai.com", "category": "ai"},
]


def _load_checks(context: RunContext) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    path = find_config(
        ["compatibility_targets.yaml", "compatibility_targets.json"],
        search_dirs=[
            context.environment.get("config_dir") or ".",
            ".",
            str(Path(__file__).resolve().parents[1] / "data"),
        ],
    )
    if not path:
        return list(DEFAULT_CHECKS), None
    data = load_config(path)
    checks = data.get("checks") or []
    out = [c for c in checks if isinstance(c, dict) and c.get("url")]
    return out or list(DEFAULT_CHECKS), str(path)


def _probe_url(url: str, timeout: float = 10.0) -> Dict[str, Any]:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "LeBench/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            # Read tiny body only
            resp.read(2048)
            return {
                "network_reachable": True,
                "http_status": int(code) if code else None,
                "page_accessible": True if code and int(code) < 500 else False,
                "account_usable": None,
            }
    except urllib.error.HTTPError as exc:
        return {
            "network_reachable": True,
            "http_status": int(exc.code),
            "page_accessible": exc.code < 500,
            "account_usable": None,
            "error": f"HTTPError:{exc.code}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "network_reachable": False,
            "http_status": None,
            "page_accessible": False,
            "account_usable": None,
            "error": f"{type(exc).__name__}",
        }


class CompatibilityModule(BenchmarkModule):
    name = "compatibility"
    description = "流媒体/AI 平台可达性（可选；HTTP 200 ≠ 完整解锁）"
    stage = "s3"
    implemented = True
    dependencies: List[str] = []
    optional_dependencies: List[str] = []

    def probe(self, context: RunContext) -> ProbeResult:
        enabled = bool(context.environment.get("enable_compatibility", False)) or context.intensity == "deep"
        return ProbeResult(
            available=True,
            reason=None if enabled else "disabled_unless_deep_or_--enable-compatibility",
            details={"enabled": enabled},
        )

    def estimate_cost(self, context: RunContext) -> CostEstimate:
        return CostEstimate(time_sec=30.0, network_mb=1.0, notes=["HTTP reachability only"])

    def run(self, context: RunContext) -> ModuleResult:
        started = time.monotonic()
        enabled = bool(context.environment.get("enable_compatibility", False)) or context.intensity == "deep"
        if not enabled:
            return ModuleResult.not_run(
                reason="compatibility_not_enabled",
                conditions={"hint": "使用 --enable-compatibility 或 deep 强度"},
                duration_sec=round(time.monotonic() - started, 3),
            )

        checks, path = _load_checks(context)
        results: List[Dict[str, Any]] = []
        warnings = [
            "http_status_ alone_does_not_mean_unlocked_or_account_usable",
            "遵守目标站点服务条款；默认仅做有限可达性探测",
        ]
        for c in checks[:20]:
            probe = _probe_url(str(c["url"]))
            results.append(
                {
                    "name": c.get("name"),
                    "category": c.get("category"),
                    "url": c["url"] if context.allow_sensitive else "<url>",
                    **probe,
                    "unlock_claimed": False,
                }
            )

        duration = round(time.monotonic() - started, 3)
        return ModuleResult(
            status=ModuleStatus.COMPLETED.value,
            metrics={"checks": results},
            conditions={
                "config": path,
                "account_usable": "not_tested",
                "judgment": "人工审核；脚本不声称完整解锁",
            },
            warnings=warnings,
            tool={"name": "lebench.compatibility", "version": "0.1.0"},
            duration_sec=duration,
        )
