"""Flask 应用工厂：创建并配置 Web 服务。

对应文档「服务层」：
以 Flask 为核心，开发 Web 服务与 RESTful API 接口，返回标准化 JSON。
"""
from datetime import timedelta

import logging
import uuid

from flask import Flask, g, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from config import AUTH_CONFIG

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """创建 Flask 应用实例（应用工厂模式，便于测试与扩展）。"""
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False  # 返回中文不转义
    app.json.ensure_ascii = False
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024
    app.config.update(
        SECRET_KEY=AUTH_CONFIG["secret_key"],
        PERMANENT_SESSION_LIFETIME=timedelta(hours=AUTH_CONFIG["hours"]),
        SESSION_COOKIE_NAME="smart_healthcare_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=AUTH_CONFIG["cookie_secure"],
        SESSION_COOKIE_SAMESITE="Lax",
    )

    # 跨域：允许前端 Vite 开发服务器 (http://localhost:5173) 访问
    CORS(app, origins=AUTH_CONFIG["allowed_origins"], supports_credentials=True)

    from app.auth.web import init_auth
    init_auth(app)

    # 注册 API 蓝图
    from app.service_layer.api.routes import api
    app.register_blueprint(api)

    @app.before_request
    def assign_request_id():
        incoming = (request.headers.get("X-Request-ID") or "").strip()
        g.request_id = incoming[:64] if incoming and all(ch.isalnum() or ch in "-_" for ch in incoming) else uuid.uuid4().hex

    @app.after_request
    def expose_request_id(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        return response

    from app.common.response import APIError, fail

    @app.errorhandler(APIError)
    def api_error(error):
        meta = {"details": error.details} if error.details is not None else None
        return fail(error.message, code=error.code, meta=meta), error.status_code

    @app.errorhandler(ValueError)
    def invalid_value(error):
        return fail(str(error), code=400), 400

    @app.errorhandler(RequestEntityTooLarge)
    def request_too_large(_error):
        return fail("请求体不能超过 1 MB", code=413), 413

    @app.errorhandler(404)
    def not_found(_error):
        return fail("接口不存在", code=404), 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return fail("请求方法不允许", code=405), 405


    @app.errorhandler(HTTPException)
    def http_error(error):
        return fail(error.description or "请求失败", code=error.code or 500), error.code or 500

    @app.errorhandler(Exception)
    def unexpected_error(error):
        logger.exception("未处理的 API 异常: %s", error.__class__.__name__)
        return fail("服务暂时不可用，请稍后重试", code=500), 500

    return app
