"""API: multi-server compare."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..db import compare_runs, db_session

router = APIRouter()


@router.get("/compare")
def api_compare(
    runs: str = Query(..., description="Comma-separated run_id list"),
) -> dict:
    ids = [x.strip() for x in runs.split(",") if x.strip()]
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="need at least 2 run_ids")
    if len(ids) > 8:
        raise HTTPException(status_code=400, detail="max 8 runs")
    with db_session() as conn:
        result = compare_runs(conn, ids)
    if len(result["runs"]) < 2:
        raise HTTPException(status_code=404, detail="not enough matching runs")
    return result
