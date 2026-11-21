"""IP quality lookups via optional user-configured APIs (keys never logged)."""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from lebench.core.result import ModuleResult, ModuleStatus
from lebench.core.safety import CostEstimate
from lebench.modules.base import BenchmarkModule, ProbeResult, RunContext


def _public_ip_best_effort() -> Optional[str]:
    for url in (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
    ):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LeBench/0.1"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                text = resp.read(64).decode("utf-8", errors="replace").strip()
                if text and " " not in text and len(text) < 64:
                    return text
        except Exception:  # noqa: BLE001
            continue
    return None


def _check_port_25(host: str = "smtp.gmail.com", timeout: float = 5.0) -> Dict[str, Any]:
    try:
        with socket.create_connection((host, 25), timeout=timeout):
            return {"reachable_outbound_25": True, "probe_host": host}
    except OSError as exc:
        return {"reachable_outbound_25": False, "probe_host": host, "error": str(exc)}


def _query_ip_api(ip: str) -> Dict[str, Any]:
    """Use free ip-api.com JSON (no key). Respect rate limits; failures → not used as truth."""
    url = f"http://ip-api.com/json/{ip}?fields=status,message,country,regionName,isp,org,as,query,proxy,hosting,mobile"
    req = urllib.request.Request(url, headers={"User-Agent": "LeBench/0.1"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read(8192).decode("utf-8", errors="replace"))
    if data.get("status") != "success":
        raise RuntimeError(data.get("message") or "ip_api_failed")
    return {
        "asn": data.get("as"),
        "isp": data.get("isp") or data.get("org"),
        "country": data.get("country"),
        "region": data.get("regionName"),
        "ip_type_hints": {
            "proxy": data.get("proxy"),
            "hosting": data.get("hosting"),
            "mobile": data.get("mobile"),
        },
        "source": "ip-api.com",
    }


def _query_custom_api(url_template: str, ip: str, api_key: str) -> Dict[str, Any]:
    url = url_template.format(ip=ip, key=api_key)
    # Ensure key not later logged — only return sanitized fields
    req = urllib.request.Request(url, headers={"User-Agent": "LeBench/0.1"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read(65536).decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw_status": "non_json", "source": "custom_api"}
    return {"data": data, "source": "custom_api"}


class IpQualityModule(BenchmarkModule):
    name = "ip_quality"
    description = "IP 质量（可选 API；密钥不写日志/报告）"
    stage = "s3"
    implemented = True
    dependencies: List[str] = []
    optional_dependencies: List[str] = []

    def probe(self, context: RunContext) -> ProbeResult:
        return ProbeResult(available=True, details={"network_required": True})

    def estimate_cost(self, context: RunContext) -> CostEstimate:
        return CostEstimate(time_sec=15.0, network_mb=0.5, notes=["external IP reputation APIs"])

    def run(self, context: RunContext) -> ModuleResult:
        started = time.monotonic()
        warnings: List[str] = []
        metrics: Dict[str, Any] = {}
        conditions: Dict[str, Any] = {
            "api_key_logged": False,
            "note": "不自动判定住宅/原生 IP 最终真实性；多库结论需人工审核",
        }

        # Port 25 outbound probe (common mail port policy signal)
        metrics["port25"] = _check_port_25()

        use_public = bool(context.environment.get("enable_ip_quality", True))
        if not use_public:
            return ModuleResult.not_run(
                reason="ip_quality_disabled",
                metrics=metrics,
                conditions=conditions,
                duration_sec=round(time.monotonic() - started, 3),
            )

        ip = _public_ip_best_effort()
        if not ip:
            return ModuleResult.not_run(
                reason="public_ip_unavailable",
                metrics=metrics,
                conditions=conditions,
                warnings=["cannot_determine_public_ip"],
                duration_sec=round(time.monotonic() - started, 3),
            )

        # Store IP only if allow_sensitive
        metrics["public_ip"] = ip if context.allow_sensitive else "<redacted>"

        api_key = os.environ.get("LEBENCH_IP_API_KEY") or context.environment.get("ip_api_key")
        api_url = os.environ.get("LEBENCH_IP_API_URL") or context.environment.get("ip_api_url")

        try:
            if api_key and api_url:
                custom = _query_custom_api(str(api_url), ip, str(api_key))
                # Strip any accidental key leakage from nested structures
                metrics["custom_lookup"] = {"source": "custom_api", "ok": True}
                metrics["lookup"] = {"source": "custom_api", "present": True}
                _ = custom  # raw may contain secrets — do not attach wholesale
                warnings.append("custom_api_queried_raw_omitted_from_report")
            else:
                lookup = _query_ip_api(ip)
                metrics["asn"] = lookup.get("asn")
                metrics["isp"] = lookup.get("isp")
                metrics["country"] = lookup.get("country")
                metrics["region"] = lookup.get("region")
                metrics["ip_type_hints"] = lookup.get("ip_type_hints")
                metrics["source"] = lookup.get("source")
                conditions["provider"] = "ip-api.com"
                warnings.append("free_ip_api_best_effort_respect_provider_tos_and_quota")
        except Exception as exc:  # noqa: BLE001
            return ModuleResult.not_run(
                reason=f"external_lookup_unavailable:{type(exc).__name__}",
                metrics=metrics,
                conditions=conditions,
                warnings=warnings + [str(exc)[:160]],
                duration_sec=round(time.monotonic() - started, 3),
                tool={"name": "lebench.ip_quality", "version": "0.1.0"},
            )

        duration = round(time.monotonic() - started, 3)
        return ModuleResult(
            status=ModuleStatus.COMPLETED.value,
            metrics=metrics,
            conditions=conditions,
            warnings=warnings,
            tool={"name": "lebench.ip_quality", "version": "0.1.0"},
            duration_sec=duration,
        )
