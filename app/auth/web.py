"""Flask session loading, CSRF checks and authorization decorators."""
from __future__ import annotations

import secrets
import time
from functools import wraps

from flask import g, request, session

from app.auth import service
from app.auth.permissions import has_permission
from app.common.response import fail
from config import AUTH_CONFIG


def init_auth(app) -> None:
    @app.before_request
    def load_current_user():
        g.current_user = None
        user_id = session.get("user_id")
        if not user_id:
            return None
        now = int(time.time())
        if now - int(session.get("last_activity", now)) > AUTH_CONFIG["idle_minutes"] * 60:
            session.clear()
            return None
        user = service.get_user(int(user_id))
        if not user or not user["is_active"]:
            session.clear()
            return None
        session["last_activity"] = now
        g.current_user = user
        return None

    @app.before_request
    def verify_csrf():
        if request.method in {"GET", "HEAD", "OPTIONS"} or request.endpoint == "api.login":
            return None
        if not session.get("user_id"):
            return None
        supplied = request.headers.get("X-CSRF-Token", "")
        if not supplied or not secrets.compare_digest(supplied, session.get("csrf_token", "")):
            return fail("CSRF 校验失败", code=403), 403
        return None


def start_session(user: dict) -> str:
    session.clear()
    session.permanent = True
    token = secrets.token_urlsafe(32)
    session.update(user_id=user["id"], csrf_token=token, last_activity=int(time.time()))
    return token


def current_user() -> dict | None:
    return getattr(g, "current_user", None)


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user():
            return fail("请先登录", code=401), 401
        return func(*args, **kwargs)
    return wrapper


def permission_required(permission: str):
    def decorator(func):
        @wraps(func)
        @login_required
        def wrapper(*args, **kwargs):
            if not has_permission(current_user(), permission):
                return fail("没有执行此操作的权限", code=403), 403
            return func(*args, **kwargs)
        return wrapper
    return decorator
