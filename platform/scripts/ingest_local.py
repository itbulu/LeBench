#!/usr/bin/env python3
"""Ingest one or more CLI result directories into the platform SQLite DB (local, no HTTP)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import build_payload_from_run_dir, db_session, init_db, upsert_run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Import LZY Bench results into platform DB")
    parser.add_argument("paths", nargs="+", help="results/<run_id> directories")
    parser.add_argument("--label", default=None)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--region", default=None)
    parser.add_argument("--price", type=float, default=None)
    args = parser.parse_args()

    init_db()
    with db_session() as conn:
        for p in args.paths:
            run_dir = Path(p).resolve()
            if not run_dir.is_dir():
                print(f"[SKIP] not a directory: {run_dir}", file=sys.stderr)
                continue
            run_id = run_dir.name
            payload = build_payload_from_run_dir(run_dir)
            rid = upsert_run(
                conn,
                run_id=run_id,
                payload=payload,
                label=args.label,
                provider=args.provider,
                region=args.region,
                price=args.price,
            )
            print(f"[OK] imported {run_id} -> id={rid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
