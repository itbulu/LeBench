"""API: ingest and query benchmark runs."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import require_token
from ..db import db_session, get_run, list_runs, upsert_run

router = APIRouter()


class IngestBody(BaseModel):
    run_id: str = Field(..., min_length=1)
    label: str | None = None
    provider: str | None = None
    region: str | None = None
    price: float | None = None
    payload: dict[str, Any]


class IngestResponse(BaseModel):
    ok: bool
    id: int
    run_id: str


@router.post("/runs", response_model=IngestResponse, dependencies=[Depends(require_token)])
def ingest_run(body: IngestBody) -> IngestResponse:
    with db_session() as conn:
        rid = upsert_run(
            conn,
            run_id=body.run_id,
            payload=body.payload,
            label=body.label,
            provider=body.provider,
            region=body.region,
            price=body.price,
        )
    return IngestResponse(ok=True, id=rid, run_id=body.run_id)


@router.get("/runs")
def api_list_runs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    order: str = Query("overall"),
) -> dict:
    with db_session() as conn:
        items = list_runs(conn, limit=limit, offset=offset, order=order)
    return {"count": len(items), "items": items}


@router.get("/runs/{run_id}")
def api_get_run(run_id: str) -> dict:
    with db_session() as conn:
        item = get_run(conn, run_id)
    if not item:
        raise HTTPException(status_code=404, detail="run not found")
    return item


@router.delete("/runs/{run_id}", dependencies=[Depends(require_token)])
def api_delete_run(run_id: str) -> dict:
    with db_session() as conn:
        cur = conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="run not found")
    return {"ok": True, "run_id": run_id}
