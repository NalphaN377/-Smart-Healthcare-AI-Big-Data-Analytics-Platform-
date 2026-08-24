import numpy as np
import pytest

from app.ml import cost_model


class FakeModel:
    def predict(self, frame):
        assert list(frame.columns) == cost_model.FEATURES
        return np.array([12345.67])


def test_predict_cost_contract(monkeypatch):
    record = {
        "id": 7, "model_version": "cost-v4-test", "training_data_version": 4,
        "holdout_year": 2024, "metrics": {"mae": 1000.0, "r2": 0.8},
    }
    monkeypatch.setattr(cost_model, "_load_active", lambda: (record, {"model": FakeModel()}))
    result = cost_model.predict_cost({
        "age_group": "50 to 69", "discharge_year": 2024,
        "length_of_stay": 5, "apr_severity_of_illness_code": 2,
    })
    assert result["predicted_total_cost"] == 12345.67
    assert result["approximate_error_band"]["lower"] == 11345.67
    assert result["model"]["training_data_version"] == 4


def test_predict_features_reject_unknown_and_invalid_values():
    with pytest.raises(ValueError, match="不支持的特征"):
        cost_model._validated_features({"total_charges": 100})
    with pytest.raises(ValueError, match="length_of_stay"):
        cost_model._validated_features({"length_of_stay": -1})


def test_metrics_are_on_original_cost_scale():
    metrics = cost_model._metrics(np.array([100.0, 300.0]), np.array([150.0, 250.0]))
    assert metrics["mae"] == 50.0
    assert metrics["rmse"] == 50.0
