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


def test_future_prediction_uses_only_pre_admission_features_and_growth(monkeypatch):
    class FutureModel:
        def predict(self, frame):
            assert list(frame.columns) == cost_model.PRE_ADMISSION_FEATURES
            return np.array([12345.67])

    record = {
        "id": 9, "model_version": "pre-admission-cost-v4-test", "holdout_year": 2024,
        "metrics": {"mae": 1000.0, "r2": 0.6},
    }
    monkeypatch.setattr(cost_model, "_load_active", lambda _name: (record, {"model": FutureModel()}))
    monkeypatch.setattr(cost_model, "_future_growth_rate", lambda: (0.02, 2024))
    result = cost_model.predict_future_cost({"age_group": "50 to 69"}, 2026)

    assert result["forecast_year"] == 2026
    assert result["predicted_total_cost"] == round(12345.67 * 1.02 ** 2, 2)
    assert result["assumptions"]["growth_rate_source"] == "historical_cagr"


def test_future_prediction_rejects_post_discharge_features(monkeypatch):
    monkeypatch.setattr(cost_model, "_load_active", lambda _name: ({"id": 1, "metrics": {}}, {"model": object()}))
    monkeypatch.setattr(cost_model, "_future_growth_rate", lambda: (0.02, 2024))
    with pytest.raises(ValueError, match="不支持的特征"):
        cost_model.predict_future_cost({"length_of_stay": 4}, 2025)


def test_budget_forecast_uses_historical_baseline_and_user_scenario(monkeypatch):
    class Cursor:
        def execute(self, sql, params):
            self.sql, self.params = sql, params

        def fetchall(self):
            return [(2021, 100, 1_000_000), (2024, 120, 1_560_000)]

    class Connection:
        def cursor(self): return Cursor()
        def close(self): pass

    monkeypatch.setattr(cost_model.storage, "get_connection", Connection)
    result = cost_model.forecast_annual_budget({
        "scope_type": "service_area", "scope_value": "New York City", "target_year": 2025,
        "annual_volume_growth_rate": 0.1, "annual_cost_growth_rate": 0.05,
    })

    assert result["forecast_case_count"] == 132
    assert result["forecast_average_cost"] == 13650.0
    assert result["forecast_total_cost"] == 1801800.0
    assert result["assumptions"]["volume_rate_source"] == "user_scenario"


def test_register_model_uses_the_requested_model_name(monkeypatch):
    class Cursor:
        def execute(self, sql, params): self.sql, self.params = sql, params
        def fetchone(self): return (12,)

    class Connection:
        def __init__(self): self.cursor_value = Cursor()
        def cursor(self): return self.cursor_value
        def commit(self): pass
        def rollback(self): pass
        def close(self): pass

    connection = Connection()
    monkeypatch.setattr(cost_model.storage, "get_connection", lambda: connection)
    metadata = {
        "model_version": "future-v1", "artifact_path": "x.joblib", "algorithm": "test",
        "training_data_version": 4, "train_rows": 1000, "test_rows": 1000, "holdout_year": 2024,
        "metrics": {}, "feature_schema": {},
    }
    model_id = cost_model._register_model(metadata, cost_model.FUTURE_MODEL_NAME)

    assert model_id == 12
    # 第一个参数属于 UPDATE，第二个参数属于 INSERT；两者必须指向同一模型名称。
    assert connection.cursor_value.params[:2] == (cost_model.FUTURE_MODEL_NAME, cost_model.FUTURE_MODEL_NAME)
