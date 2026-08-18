from __future__ import annotations

from flask import Blueprint, current_app, request
from pydantic import ValidationError as PydanticValidationError

from backend.ml import CostPredictionRequest, ModelUnavailableError

from ..utils.responses import error_response, success_response


blueprint = Blueprint("ml", __name__)


def service():
    return current_app.extensions["cost_prediction_service"]


@blueprint.get("/api/ml/cost-prediction/status")
def status():
    return success_response(service().status(), {"component": "cost_prediction"})


@blueprint.post("/api/ml/cost-prediction/predict")
def predict():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error_response("JSON request body is required", 400)
    try:
        parsed = CostPredictionRequest.model_validate(payload)
        result = service().predict(parsed)
    except PydanticValidationError as error:
        safe_errors = [
            {
                "location": list(item["loc"]),
                "message": item["msg"],
                "type": item["type"],
            }
            for item in error.errors(include_url=False)
        ]
        return error_response(
            "Cost prediction input validation failed",
            400,
            {"component": "cost_prediction", "errors": safe_errors},
        )
    except ModelUnavailableError:
        return error_response(
            "Cost prediction model is unavailable; train the model first",
            503,
            {"component": "cost_prediction"},
        )
    except ValueError as error:
        return error_response(
            str(error),
            400,
            {"component": "cost_prediction"},
        )
    return success_response(result, {"component": "cost_prediction"})
