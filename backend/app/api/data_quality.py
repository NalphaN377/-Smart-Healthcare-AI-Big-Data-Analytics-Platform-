from flask import Blueprint, current_app

from ..utils.responses import error_response, success_response


blueprint = Blueprint("data_quality", __name__)


def service():
    return current_app.extensions["data_quality_service"]


@blueprint.get("/api/data-quality/summary")
def summary():
    try:
        data = service().summary()
    except (FileNotFoundError, ValueError):
        return error_response(
            "Data quality metrics are unavailable; run the metrics generator",
            503,
            {"component": "data_quality"},
        )
    return success_response(data, {"component": "data_quality", "snapshot": True})


@blueprint.get("/api/data-quality/fields")
def fields():
    try:
        data = service().fields()
    except (FileNotFoundError, ValueError):
        return error_response(
            "Data quality metrics are unavailable; run the metrics generator",
            503,
            {"component": "data_quality"},
        )
    return success_response(
        data,
        {"component": "data_quality", "snapshot": True, "count": len(data)},
    )
