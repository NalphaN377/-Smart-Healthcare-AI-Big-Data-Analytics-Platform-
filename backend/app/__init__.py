from __future__ import annotations

import logging

import pymysql
from flask import Flask
from flask_cors import CORS

from .ai import InMemoryConversationStore, MedicalAnalyticsAgent, ToolRegistry, build_provider
from .api import age, ai, cost, disease, health, hospital, overview, payment, severity, trends
from .api.params import ValidationError
from .config import Config
from .repositories.analytics_repository import AnalyticsRepository
from .utils.responses import error_response


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    repository = app.config.get("ANALYTICS_REPOSITORY") or AnalyticsRepository(app.config)
    app.extensions["analytics_repository"] = repository
    tool_registry = app.config.get("AI_TOOL_REGISTRY") or ToolRegistry(repository)
    conversation_store = app.config.get("AI_CONVERSATION_STORE") or InMemoryConversationStore(
        max_turns=app.config["AI_MAX_TURNS"],
        max_sessions=app.config["AI_MAX_SESSIONS"],
    )
    provider = app.config.get("AI_PROVIDER_INSTANCE") or build_provider(app.config)
    app.extensions["ai_tool_registry"] = tool_registry
    app.extensions["ai_conversation_store"] = conversation_store
    app.extensions["ai_provider"] = provider
    app.extensions["medical_analytics_agent"] = MedicalAnalyticsAgent(
        provider=provider,
        registry=tool_registry,
        conversation_store=conversation_store,
    )

    for api_blueprint in (
        health.blueprint,
        overview.blueprint,
        disease.blueprint,
        hospital.blueprint,
        cost.blueprint,
        age.blueprint,
        payment.blueprint,
        severity.blueprint,
        trends.blueprint,
        ai.blueprint,
    ):
        app.register_blueprint(api_blueprint)

    @app.errorhandler(ValidationError)
    def handle_validation_error(error):
        return error_response(str(error), 400)

    @app.errorhandler(pymysql.MySQLError)
    def handle_database_error(error):
        app.logger.warning("Database request failed: %s", error.__class__.__name__)
        return error_response("Database query failed or the database is unavailable", 503)

    @app.errorhandler(404)
    def handle_not_found(_error):
        return error_response("API endpoint not found", 404)

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        app.logger.exception("Unhandled API error")
        return error_response("Internal server error", 500)

    if not app.debug:
        logging.getLogger("werkzeug").setLevel(logging.INFO)
    return app


__all__ = ["create_app"]
