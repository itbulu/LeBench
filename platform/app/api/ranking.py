"""API: rankings."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..db import db_session, ranking

router = APIRouter()


@router.get("/ranking")
def api_ranking(
    metric: str = Query("overall"),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    with db_session() as conn:
        items = ranking(conn, metric=metric, limit=limit)
    return {"metric": metric, "count": len(items), "items": items}
