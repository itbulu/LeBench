"""LZY Bench Platform — FastAPI application."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import compare, ranking, runs
from .db import init_db

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="LZY Bench Platform",
    description="LeZaiYun Benchmark Toolkit — API & Dashboard (Phase 4)",
    version="1.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs.router, prefix="/api", tags=["runs"])
app.include_router(ranking.router, prefix="/api", tags=["ranking"])
app.include_router(compare.router, prefix="/api", tags=["compare"])


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "lzy-bench-platform", "version": "1.3.0"}


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
