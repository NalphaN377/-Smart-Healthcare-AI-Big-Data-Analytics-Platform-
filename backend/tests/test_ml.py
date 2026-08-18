from __future__ import annotations

import json

import joblib
import pytest
from pydantic import ValidationError

from backend.ml.schemas import CostPredictionRequest
from backend.ml.service import CostPredictionService, ModelUnavailableError
from backend.ml.train_cost_model import FEATURES, LEAKAGE_EXCLUSIONS, TARGET


VALID_INPUT = {
    "age_group": "70 or Older",
    "gender": "F",
    "admission_type": "Emergency",
    "diagnosis_code": "CIR001",
    "severity": "Major",
    "mortality_risk": "Moderate",
    "medical_surgical_description": "Medical",
    "emergency_indicator": True,
    "payment_type_1": "Medicare",
}


class ConstantCostModel:
    def predict(self, _frame):
        return [12345.678]


class FakeMLService:
    def __init__(self, available=True):
        self.available = available

    def status(self):
        return {
            "available": self.available,
            "model_version": "test-v1" if self.available else None,
            "features": FEATURES if self.available else [],
            "feature_options": {},
            "metrics": {},
            "sample_size": 100,
            "disclaimer": "test disclaimer",
        }

    def predict(self, request):
        if not self.available:
            raise ModelUnavailableError
        return {
            "predicted_cost": 123.45,
            "model_version": "test-v1",
            "features_used": FEATURES,
            "disclaimer": "test disclaimer",
        }


def build_service(tmp_path):
    model_path = tmp_path / "model.joblib"
    metadata_path = tmp_path / "metadata.json"
    joblib.dump(ConstantCostModel(), model_path)
    metadata_path.write_text(
        json.dumps(
            {
                "model_version": "test-v1",
                "target": TARGET,
                "features": FEATURES,
                "feature_options": {"diagnosis_code": ["CIR001"]},
                "metrics": {"mae": 100.0},
                "sample_size": 100,
            }
        ),
        encoding="utf-8",
    )
    return CostPredictionService(model_path, metadata_path)


def test_model_features_exclude_cost_and_metadata_leakage():
    assert TARGET not in FEATURES
    assert "total_charges" not in FEATURES
    assert "length_of_stay" not in FEATURES
    assert set(FEATURES).isdisjoint(LEAKAGE_EXCLUSIONS)


def test_prediction_schema_normalizes_diagnosis_code_and_forbids_extra_fields():
    parsed = CostPredictionRequest.model_validate({**VALID_INPUT, "diagnosis_code": "cir001"})
    assert parsed.diagnosis_code == "CIR001"
    with pytest.raises(ValidationError):
        CostPredictionRequest.model_validate({**VALID_INPUT, "total_charges": 1000})


def test_prediction_schema_rejects_invalid_category():
    with pytest.raises(ValidationError):
        CostPredictionRequest.model_validate({**VALID_INPUT, "age_group": "Senior"})


def test_service_status_and_inference(tmp_path):
    service = build_service(tmp_path)
    assert service.status()["available"] is True
    result = service.predict(CostPredictionRequest.model_validate(VALID_INPUT))
    assert result["predicted_cost"] == 12345.68
    assert result["features_used"] == FEATURES
    assert "不构成医疗" in result["disclaimer"]


def test_service_rejects_diagnosis_not_seen_during_training(tmp_path):
    service = build_service(tmp_path)
    request = CostPredictionRequest.model_validate(
        {**VALID_INPUT, "diagnosis_code": "ZZZ999"}
    )
    with pytest.raises(ValueError, match="trained dataset"):
        service.predict(request)


def test_service_is_explicitly_unavailable_without_artifact(tmp_path):
    service = CostPredictionService(tmp_path / "missing.joblib", tmp_path / "missing.json")
    assert service.status()["available"] is False
    with pytest.raises(ModelUnavailableError):
        service.predict(CostPredictionRequest.model_validate(VALID_INPUT))


def test_ml_api_status_and_prediction(client, app):
    app.extensions["cost_prediction_service"] = FakeMLService()
    status = client.get("/api/ml/cost-prediction/status")
    response = client.post("/api/ml/cost-prediction/predict", json=VALID_INPUT)
    assert status.status_code == 200
    assert status.get_json()["data"]["available"] is True
    assert response.status_code == 200
    assert response.get_json()["data"]["predicted_cost"] == 123.45


def test_ml_api_returns_safe_validation_and_unavailable_errors(client, app):
    invalid = client.post(
        "/api/ml/cost-prediction/predict", json={**VALID_INPUT, "gender": "X"}
    )
    assert invalid.status_code == 400
    assert "validation" in invalid.get_json()["message"].lower()

    app.extensions["cost_prediction_service"] = FakeMLService(available=False)
    unavailable = client.post("/api/ml/cost-prediction/predict", json=VALID_INPUT)
    assert unavailable.status_code == 503
    assert unavailable.get_json()["data"] is None
    assert "traceback" not in unavailable.get_data(as_text=True).lower()
