from flask import Blueprint, current_app, request
from pydantic import ValidationError as PydanticValidationError

from ..ai.errors import (
    ProviderFailure,
    ProviderNotConfigured,
    ProviderTimeout,
    ToolValidationFailure,
    UnsupportedQuery,
)
from ..ai.schemas import AIQueryRequest
from ..utils.responses import error_response, success_response


blueprint = Blueprint("ai", __name__)


@blueprint.post("/api/ai/query")
def ai_query():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("JSON request body is required", 400)
    try:
        parsed = AIQueryRequest.model_validate(payload)
        data, meta = current_app.extensions["medical_analytics_agent"].query(
            parsed.query,
            parsed.session_id,
        )
    except PydanticValidationError as error:
        safe_errors = [
            {"location": list(item["loc"]), "message": item["msg"], "type": item["type"]}
            for item in error.errors(include_url=False)
        ]
        return error_response("AI query validation failed", 400, {"errors": safe_errors})
    except ProviderNotConfigured:
        return error_response("LLM provider not configured", 503, {"component": "ai_provider"})
    except ProviderTimeout:
        return error_response("LLM provider request timed out", 504, {"component": "ai_provider"})
    except ToolValidationFailure as error:
        return error_response("AI tool validation failed", 400, {"detail": str(error)})
    except UnsupportedQuery:
        return error_response("Unsupported analytics question", 422, {"component": "ai_router"})
    except ProviderFailure:
        return error_response("LLM provider request failed", 502, {"component": "ai_provider"})
    return success_response(data.model_dump(mode="json"), meta)


@blueprint.get("/api/ai/status")
def ai_status():
    provider = current_app.extensions["ai_provider"]
    return success_response(
        {
            "configured": provider.configured,
            "provider": provider.public_info,
            "max_turns": current_app.config["AI_MAX_TURNS"],
        },
        {"component": "ai_provider"},
    )
