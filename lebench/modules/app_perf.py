"""Optional isolated lightweight HTTP concurrency probe — requires explicit enable."""

from __future__ import annotations

import http.server
import statistics
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from lebench.core.result import ModuleResult, ModuleStatus
from lebench.core.safety import CostEstimate
from lebench.modules.base import BenchmarkModule, ProbeResult, RunContext


class _QuietHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args):  # noqa: A003
        return


class AppPerfModule(BenchmarkModule):
    name = "app_perf"
    description = "可选隔离环境轻量 HTTP 并发探活（需 --enable-app-perf）"
    stage = "s4"
    implemented = True
    dependencies: List[str] = []
    optional_dependencies: List[str] = []

    def probe(self, context: RunContext) -> ProbeResult:
        enabled = bool(context.environment.get("enable_app_perf"))
        return ProbeResult(
            available=True,
            reason=None if enabled else "requires_--enable-app-perf",
            details={"enabled": enabled, "isolated_local_server": True},
        )

    def estimate_cost(self, context: RunContext) -> CostEstimate:
        return CostEstimate(
            time_sec=20.0,
            cpu_heavy=True,
            risks=["local_load"],
            notes=["local loopback only; limited concurrency"],
        )

    def run(self, context: RunContext) -> ModuleResult:
        started = time.monotonic()
        if not context.environment.get("enable_app_perf"):
            return ModuleResult.not_run(
                reason="app_perf_requires_explicit_enable",
                conditions={
                    "hint": "lebench run ... --enable-app-perf",
                    "note": "不测控制台镜像/快照/备份等产品能力",
                },
                duration_sec=round(time.monotonic() - started, 3),
            )

        # Bind ephemeral local port
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        url = f"http://127.0.0.1:{port}/"
        concurrency = 8
        requests_n = 64
        latencies: List[float] = []
        errors = 0

        def one() -> float:
            t0 = time.perf_counter()
            with urllib.request.urlopen(url, timeout=5) as resp:
                resp.read()
            return (time.perf_counter() - t0) * 1000

        try:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futs = [pool.submit(one) for _ in range(requests_n)]
                for fut in as_completed(futs):
                    try:
                        latencies.append(fut.result())
                    except Exception:  # noqa: BLE001
                        errors += 1
        finally:
            server.shutdown()
            server.server_close()

        duration = round(time.monotonic() - started, 3)
        if not latencies:
            return ModuleResult.failed(
                reason="app_perf_all_requests_failed",
                duration_sec=duration,
            )

        metrics = {
            "concurrency": concurrency,
            "requests": requests_n,
            "errors": errors,
            "latency_ms_avg": round(statistics.mean(latencies), 3),
            "latency_ms_p50": round(statistics.median(latencies), 3),
            "latency_ms_max": round(max(latencies), 3),
            "rps_approx": round(len(latencies) / max(duration, 0.001), 2),
            "endpoint": "loopback_ephemeral",
        }
        return ModuleResult(
            status=ModuleStatus.COMPLETED.value if errors == 0 else ModuleStatus.PARTIAL.value,
            metrics=metrics,
            conditions={
                "isolated": True,
                "cleaned_up": True,
                "wordpress_or_containers": "not_installed",
                "note": "本地回环轻量压测，不代表真实站点/镜像性能",
            },
            tool={"name": "lebench.app_perf", "version": "0.1.0"},
            duration_sec=duration,
        )
