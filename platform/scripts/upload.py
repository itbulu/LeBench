#!/usr/bin/env python3
"""Upload a CLI result directory to the platform HTTP API."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("[ERROR] need httpx: pip install httpx", file=sys.stderr)
    raise SystemExit(1)

# Allow importing app.db helpers without installing package
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.db import build_payload_from_run_dir  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload LZY Bench run to platform API")
    parser.add_argument("run_dir", help="path to results/<run_id>")
    parser.add_argument(
        "--api",
        default=os.environ.get("LZY_PLATFORM_API", "http://127.0.0.1:8787"),
        help="platform base URL",
    )
    parser.add_argument("--label", default=None)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--region", default=None)
    parser.add_argument("--price", type=float, default=None)
    parser.add_argument("--token", default=os.environ.get("LZY_PLATFORM_TOKEN", ""))
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print(f"[ERROR] not a directory: {run_dir}", file=sys.stderr)
        return 1

    payload = build_payload_from_run_dir(run_dir)
    body = {
        "run_id": run_dir.name,
        "label": args.label,
        "provider": args.provider,
        "region": args.region,
        "price": args.price,
        "payload": payload,
    }
    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"

    url = args.api.rstrip("/") + "/api/runs"
    with httpx.Client(timeout=30.0) as client:
        r = client.post(url, json=body, headers=headers)
        if r.status_code >= 400:
            print(f"[ERROR] {r.status_code}: {r.text}", file=sys.stderr)
            return 1
        print(json.dumps(r.json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
