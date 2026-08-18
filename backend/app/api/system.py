from flask import Blueprint, current_app

from ..utils.responses import success_response


blueprint = Blueprint("system", __name__)


@blueprint.get("/api/system/cache/status")
def cache_status():
    cache = current_app.extensions["analytics_cache"]
    return success_response(cache.status(), {"component": "analytics_cache"})
