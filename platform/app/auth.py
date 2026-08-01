"""Optional Bearer token auth for mutating endpoints."""
from __future__ import annotations

import os

from fastapi import Header, HTTPException


def require_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("LZY_PLATFORM_TOKEN", "").strip()
    if not expected:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization[len("Bearer ") :].strip()
    if token != expected:
        raise HTTPException(status_code=403, detail="invalid token")
