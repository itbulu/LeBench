#!/usr/bin/env python3
"""Seed demo ranking data for local dashboard preview."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import db_session, init_db, upsert_run, utc_now  # noqa: E402


def make_payload(run_id: str, hostname: str, overall: float, scores: dict, **extra) -> dict:
    return {
        "files": {
            "meta": {
                "version": "1.3.0-platform",
                "hostname": hostname,
                "started_at": utc_now(),
                "run_id": run_id,
            },
            "summary": {"finished_at": utc_now()},
            "score": {"overall": overall, "scores": scores, "price_input": extra.get("price")},
            "system": {
                "os": {"hostname": hostname, "pretty_name": "Ubuntu 24.04 LTS"},
                "cpu": {"model": extra.get("cpu_model", "Demo CPU")},
                "network": {"public_ip": extra.get("ip", "1.2.3.4")},
            },
            "route": {"summary": {"best_guess": extra.get("route", "CN2")}, "public_ip": extra.get("ip")},
        }
    }


DEMOS = [
    ("demo-hk-01", "hk-lite-01", 9.2, {"cpu": 9.0, "memory": 8.8, "disk": 9.1, "network": 9.5, "route": 9.5, "application": 8.7},
     {"label": "HK CN2 Lite", "provider": "DemoCloud", "region": "HK", "price": 4.99, "route": "CN2", "cpu_model": "E5-2680 v4"}),
    ("demo-sg-01", "sg-ssd-01", 8.6, {"cpu": 8.5, "memory": 8.2, "disk": 9.0, "network": 8.8, "route": 7.5, "application": 8.4},
     {"label": "SG Premium", "provider": "OceanVPS", "region": "SG", "price": 6.5, "route": "CMI", "cpu_model": "Ryzen 9 5950X"}),
    ("demo-us-01", "la-budget", 7.4, {"cpu": 7.8, "memory": 7.5, "disk": 7.2, "network": 7.9, "route": 6.0, "application": 7.0},
     {"label": "LA Budget", "provider": "BudgetHost", "region": "US-LA", "price": 2.99, "route": "BACKBONE", "cpu_model": "Xeon Silver"}),
]


def main() -> int:
    init_db()
    with db_session() as conn:
        for run_id, host, overall, scores, meta in DEMOS:
            payload = make_payload(run_id, host, overall, scores, **meta)
            rid = upsert_run(
                conn,
                run_id=run_id,
                payload=payload,
                label=meta["label"],
                provider=meta["provider"],
                region=meta["region"],
                price=meta["price"],
            )
            print(f"[OK] seeded {run_id} id={rid} overall={overall}")
    print("Open http://127.0.0.1:8787/ after starting ./run.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
