from __future__ import annotations

import time

from flask import Blueprint

from ..utils.responses import error_response, success_response
from .common import repository


blueprint = Blueprint("health", __name__)


@blueprint.get("/api/health")
def health():
    started = time.perf_counter()
    try:
        database_ok = repository().ping()
    except Exception:
        return error_response(
            "API is running, but the database is unavailable",
            503,
            {"api": "ok", "database": "unavailable"},
        )
    return success_response(
        {"api": "ok", "database": "ok" if database_ok else "unavailable"},
        {"elapsed_ms": round((time.perf_counter() - started) * 1000, 2)},
        200 if database_ok else 503,
    )

