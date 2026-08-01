"""LZY Bench Platform — database layer (SQLite)."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

PLATFORM_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PLATFORM_ROOT / "data" / "lzy_bench.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_db_path() -> Path:
    return Path(os.environ.get("LZY_PLATFORM_DB", str(DEFAULT_DB)))


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    label TEXT,
    hostname TEXT,
    provider TEXT,
    region TEXT,
    price REAL,
    tool_version TEXT,
    overall REAL,
    cpu_score REAL,
    memory_score REAL,
    disk_score REAL,
    network_score REAL,
    route_score REAL,
    application_score REAL,
    price_score REAL,
    cpu_model TEXT,
    os_name TEXT,
    public_ip TEXT,
    route_guess TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_overall ON runs(overall DESC);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_label ON runs(label);
"""


def init_db(db_path: Path | None = None) -> Path:
    path = db_path or get_db_path()
    with db_session(path) as conn:
        conn.executescript(SCHEMA)
    return path


def _f(v: Any) -> float | None:
    if v is None or v == "" or v == "null":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _s(v: Any) -> str | None:
    if v is None or v == "" or v == "null":
        return None
    return str(v)


def build_payload_from_run_dir(run_dir: Path) -> dict[str, Any]:
    """Assemble a platform payload from a CLI results/<run_id>/ directory."""
    data: dict[str, Any] = {"run_dir": str(run_dir), "files": {}}
    for name in (
        "meta",
        "summary",
        "score",
        "system",
        "cpu",
        "memory",
        "disk",
        "network",
        "route",
        "streaming",
        "application",
    ):
        path = run_dir / f"{name}.json"
        if path.is_file():
            try:
                data["files"][name] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data["files"][name] = {"error": "invalid json"}
    return data


def upsert_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    payload: dict[str, Any],
    label: str | None = None,
    provider: str | None = None,
    region: str | None = None,
    price: float | None = None,
) -> int:
    files = payload.get("files") or payload
    meta = files.get("meta") or {}
    score = files.get("score") or {}
    system = files.get("system") or {}
    route = files.get("route") or {}
    summary = files.get("summary") or {}
    scores = score.get("scores") or {}

    overall = _f(score.get("overall"))
    hostname = _s((system.get("os") or {}).get("hostname")) or _s(meta.get("hostname"))
    cpu_model = _s((system.get("cpu") or {}).get("model"))
    os_name = _s((system.get("os") or {}).get("pretty_name"))
    public_ip = _s((system.get("network") or {}).get("public_ip")) or _s(
        (route.get("public_ip"))
    )
    route_guess = _s((route.get("summary") or {}).get("best_guess"))
    tool_version = _s(meta.get("version"))
    started_at = _s(meta.get("started_at"))
    finished_at = _s(summary.get("finished_at")) or _s(score.get("timestamp"))

    # Prefer explicit price arg, then payload, then score.price_input
    if price is None:
        price = _f(payload.get("price"))
    if price is None:
        price = _f(score.get("price_input"))

    label = label or _s(payload.get("label")) or hostname or run_id
    provider = provider or _s(payload.get("provider"))
    region = region or _s(payload.get("region"))

    created = utc_now()
    payload_json = json.dumps(payload, ensure_ascii=False)

    conn.execute(
        """
        INSERT INTO runs (
            run_id, label, hostname, provider, region, price, tool_version,
            overall, cpu_score, memory_score, disk_score, network_score,
            route_score, application_score, price_score,
            cpu_model, os_name, public_ip, route_guess,
            started_at, finished_at, created_at, payload_json
        ) VALUES (
            ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
        )
        ON CONFLICT(run_id) DO UPDATE SET
            label=excluded.label,
            hostname=excluded.hostname,
            provider=excluded.provider,
            region=excluded.region,
            price=excluded.price,
            tool_version=excluded.tool_version,
            overall=excluded.overall,
            cpu_score=excluded.cpu_score,
            memory_score=excluded.memory_score,
            disk_score=excluded.disk_score,
            network_score=excluded.network_score,
            route_score=excluded.route_score,
            application_score=excluded.application_score,
            price_score=excluded.price_score,
            cpu_model=excluded.cpu_model,
            os_name=excluded.os_name,
            public_ip=excluded.public_ip,
            route_guess=excluded.route_guess,
            started_at=excluded.started_at,
            finished_at=excluded.finished_at,
            payload_json=excluded.payload_json
        """,
        (
            run_id,
            label,
            hostname,
            provider,
            region,
            price,
            tool_version,
            overall,
            _f(scores.get("cpu")),
            _f(scores.get("memory")),
            _f(scores.get("disk")),
            _f(scores.get("network")),
            _f(scores.get("route")),
            _f(scores.get("application")),
            _f(scores.get("price")),
            cpu_model,
            os_name,
            public_ip,
            route_guess,
            started_at,
            finished_at,
            created,
            payload_json,
        ),
    )
    row = conn.execute("SELECT id FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return int(row["id"])


def row_to_dict(row: sqlite3.Row, include_payload: bool = False) -> dict[str, Any]:
    d = dict(row)
    if not include_payload:
        d.pop("payload_json", None)
    else:
        try:
            d["payload"] = json.loads(d.pop("payload_json") or "{}")
        except json.JSONDecodeError:
            d["payload"] = {}
            d.pop("payload_json", None)
    return d


def list_runs(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
    offset: int = 0,
    order: str = "overall",
) -> list[dict[str, Any]]:
    col = "overall" if order not in {"overall", "created_at", "price"} else order
    direction = "ASC" if col == "price" else "DESC"
    rows = conn.execute(
        f"""
        SELECT id, run_id, label, hostname, provider, region, price, tool_version,
               overall, cpu_score, memory_score, disk_score, network_score,
               route_score, application_score, price_score,
               cpu_model, os_name, public_ip, route_guess,
               started_at, finished_at, created_at
        FROM runs
        ORDER BY CASE WHEN {col} IS NULL THEN 1 ELSE 0 END, {col} {direction}
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()
    return [row_to_dict(r) for r in rows]


def get_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if not row:
        return None
    return row_to_dict(row, include_payload=True)


def ranking(
    conn: sqlite3.Connection,
    *,
    metric: str = "overall",
    limit: int = 20,
) -> list[dict[str, Any]]:
    allowed = {
        "overall",
        "cpu_score",
        "memory_score",
        "disk_score",
        "network_score",
        "route_score",
        "application_score",
        "price_score",
    }
    col = metric if metric in allowed else "overall"
    rows = conn.execute(
        f"""
        SELECT id, run_id, label, hostname, provider, region, price, overall,
               cpu_score, memory_score, disk_score, network_score,
               route_score, application_score, route_guess, cpu_model, created_at
        FROM runs
        WHERE {col} IS NOT NULL
        ORDER BY {col} DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    out = []
    for i, r in enumerate(rows, start=1):
        item = row_to_dict(r)
        item["rank"] = i
        item["metric"] = col
        item["metric_value"] = item.get(col)
        out.append(item)
    return out


def compare_runs(conn: sqlite3.Connection, run_ids: list[str]) -> dict[str, Any]:
    runs = []
    for rid in run_ids:
        row = conn.execute(
            """
            SELECT id, run_id, label, hostname, provider, region, price, overall,
                   cpu_score, memory_score, disk_score, network_score,
                   route_score, application_score, price_score,
                   cpu_model, os_name, route_guess, public_ip, created_at
            FROM runs WHERE run_id = ?
            """,
            (rid,),
        ).fetchone()
        if row:
            runs.append(row_to_dict(row))

    metrics = [
        "overall",
        "cpu_score",
        "memory_score",
        "disk_score",
        "network_score",
        "route_score",
        "application_score",
        "price",
    ]
    deltas: dict[str, Any] = {}
    if len(runs) >= 2:
        base = runs[0]
        for m in metrics:
            deltas[m] = []
            for r in runs[1:]:
                a, b = base.get(m), r.get(m)
                if a is None or b is None:
                    deltas[m].append(None)
                else:
                    deltas[m].append(round(float(b) - float(a), 2))

    return {"runs": runs, "metrics": metrics, "deltas_vs_first": deltas}
