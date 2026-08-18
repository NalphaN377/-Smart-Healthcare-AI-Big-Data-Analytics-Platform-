from flask import Blueprint, request

from ..utils.responses import error_response


blueprint = Blueprint("ai", __name__)


@blueprint.post("/api/ai/query")
def ai_query():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("JSON request body is required", 400)
    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        return error_response("query must be a non-empty string", 400)
    if len(query.strip()) > 2_000:
        return error_response("query must not exceed 2000 characters", 400)
    return error_response("AI module reserved for Phase 2", 501, {"phase": 2})

