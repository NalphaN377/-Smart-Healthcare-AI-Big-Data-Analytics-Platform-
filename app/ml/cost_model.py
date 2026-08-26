"""住院记录最终总成本估算模型的训练、登记与推理。"""
from __future__ import annotations

import json
import math
import os
import warnings
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import numpy as np
import pandas as pd

from app.data_layer import storage
from config import MODEL_DIR

os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))
warnings.filterwarnings(
    "ignore", message="Could not find the number of physical cores.*",
    category=UserWarning, module=r"joblib\.externals\.loky\.backend\.context",
)

MODEL_NAME = "inpatient_total_cost"
FUTURE_MODEL_NAME = "pre_admission_future_cost"
CATEGORICAL_FEATURES = [
    "hospital_service_area", "hospital_county", "age_group", "gender", "race", "ethnicity",
    "type_of_admission", "ccsr_diagnosis_code", "ccsr_procedure_code", "apr_drg_code",
    "apr_mdc_code", "apr_severity_of_illness_desc", "apr_risk_of_mortality",
    "apr_medical_surgical_desc", "payment_typology_1", "emergency_department_indicator",
]
NUMERIC_FEATURES = ["discharge_year", "length_of_stay", "apr_severity_of_illness_code"]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES
TARGET = "total_costs"

# 仅保留在入院前可合理取得的字段。住院日、最终手术/DRG/APR 分组等不能用于
# 待入院病例预测，否则会把出院后的信息泄漏到预测中。
PRE_ADMISSION_CATEGORICAL_FEATURES = [
    "hospital_service_area", "hospital_county", "age_group", "gender", "race", "ethnicity",
    "type_of_admission", "ccsr_diagnosis_code", "payment_typology_1",
    "emergency_department_indicator",
]
PRE_ADMISSION_NUMERIC_FEATURES: list[str] = []
PRE_ADMISSION_FEATURES = PRE_ADMISSION_CATEGORICAL_FEATURES + PRE_ADMISSION_NUMERIC_FEATURES

_model_lock = Lock()
_loaded_id: int | None = None
_loaded_artifact: dict | None = None


def _fetch_year(year: int, sample_size: int, features: list[str] = FEATURES) -> pd.DataFrame:
    # discharge_year 只用于按时间划分训练/测试集；未来病例模型不会把它输入模型。
    selected = list(dict.fromkeys([*features, "discharge_year", TARGET]))
    columns = ",".join(f"[{name}]" for name in selected)
    sql = (
        f"SELECT TOP {int(sample_size)} {columns} FROM {storage.TABLE_NAME} "
        f"WHERE discharge_year={storage.PARAM} AND total_costs>0 AND total_costs<=1000000 "
        "AND ABS(CAST(CHECKSUM(id) AS BIGINT)) % 29=0 ORDER BY id"
    )
    conn = storage.get_connection(query_timeout=300)
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (int(year),))
        columns = [column[0] for column in cursor.description]
        return pd.DataFrame.from_records(cursor.fetchall(), columns=columns)
    finally:
        conn.close()


def fetch_training_data(sample_per_year: int = 50_000, features: list[str] = FEATURES) -> tuple[pd.DataFrame, int]:
    if not 1_000 <= int(sample_per_year) <= 200_000:
        raise ValueError("sample_per_year 必须在 1000 到 200000 之间")
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT DISTINCT discharge_year FROM {storage.TABLE_NAME} "
            "WHERE discharge_year IS NOT NULL ORDER BY discharge_year"
        )
        years = [int(row[0]) for row in cursor.fetchall()]
    finally:
        conn.close()
    if len(years) < 2:
        raise ValueError("至少需要两个出院年份，才能进行时间外验证")
    frames = [_fetch_year(year, int(sample_per_year), features) for year in years]
    data = pd.concat(frames, ignore_index=True)
    if data.empty:
        raise ValueError("未查询到可用于训练的有效成本数据")
    return data, max(years)


def _pipeline(categorical_features: list[str] = CATEGORICAL_FEATURES, numeric_features: list[str] = NUMERIC_FEATURES):
    from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OrdinalEncoder

    categorical = Pipeline([
        ("imputer", SimpleImputer(strategy="constant", fill_value="UNKNOWN")),
        ("encoder", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
    ])
    numeric = SimpleImputer(strategy="median")
    transform = ColumnTransformer([
        ("categorical", categorical, categorical_features),
        ("numeric", numeric, numeric_features),
    ])
    regressor = Pipeline([
        ("features", transform),
        ("model", HistGradientBoostingRegressor(
            learning_rate=0.08, max_iter=180, max_leaf_nodes=31,
            l2_regularization=1.0, random_state=42,
        )),
    ])
    return TransformedTargetRegressor(
        regressor=regressor, func=np.log1p, inverse_func=np.expm1, check_inverse=False,
    )


def _metrics(y_true, y_pred) -> dict:
    from sklearn.metrics import mean_absolute_error, mean_squared_error, median_absolute_error, r2_score

    return {
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 2),
        "rmse": round(float(math.sqrt(mean_squared_error(y_true, y_pred))), 2),
        "median_absolute_error": round(float(median_absolute_error(y_true, y_pred)), 2),
        "r2": round(float(r2_score(y_true, y_pred)), 4),
    }


def _register_model(metadata: dict, model_name: str = MODEL_NAME) -> int:
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE dbo.ml_model SET status='archived' WHERE model_name={storage.PARAM} AND status='active'; "
            "INSERT INTO dbo.ml_model(model_name,model_version,artifact_path,algorithm,training_data_version,"
            "train_rows,test_rows,holdout_year,metrics_json,feature_schema_json,status,activated_at) "
            "OUTPUT INSERTED.id VALUES ("
            f"{','.join([storage.PARAM] * 11)},SYSUTCDATETIME())",
            (
                model_name,
                model_name, metadata["model_version"], metadata["artifact_path"], metadata["algorithm"],
                metadata["training_data_version"], metadata["train_rows"], metadata["test_rows"],
                metadata["holdout_year"], json.dumps(metadata["metrics"], ensure_ascii=False),
                json.dumps(metadata["feature_schema"], ensure_ascii=False), "active",
            ),
        )
        model_id = int(cursor.fetchone()[0])
        conn.commit()
        return model_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _train_model(
    *, model_name: str, features: list[str], categorical_features: list[str], numeric_features: list[str],
    sample_per_year: int = 50_000,
) -> dict:
    """训练并激活模型；最大年份只用于时间外测试。"""
    import joblib

    storage.init_schema()
    data, holdout_year = fetch_training_data(sample_per_year, features)
    train = data[data["discharge_year"] < holdout_year].copy()
    test = data[data["discharge_year"] == holdout_year].copy()
    if len(train) < 1_000 or len(test) < 1_000:
        raise ValueError("训练集或时间外测试集不足 1000 条")

    model = _pipeline(categorical_features, numeric_features)
    model.fit(train[features], train[TARGET].astype(float))
    predictions = np.maximum(model.predict(test[features]), 0)
    metrics = _metrics(test[TARGET].astype(float), predictions)
    data_version = storage.get_data_version()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = "cost" if model_name == MODEL_NAME else "pre-admission-cost"
    version = f"{prefix}-v{data_version}-{timestamp}"
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = (MODEL_DIR / f"{version}.joblib").resolve()
    artifact = {
        "model": model,
        "model_version": version,
        "features": features,
        "categorical_features": categorical_features,
        "numeric_features": numeric_features,
        "metrics": metrics,
        "holdout_year": holdout_year,
        "trained_at": timestamp,
    }
    temporary = artifact_path.with_suffix(".joblib.tmp")
    joblib.dump(artifact, temporary)
    temporary.replace(artifact_path)
    metadata = {
        "model_version": version,
        "artifact_path": str(artifact_path),
        "algorithm": "OrdinalEncoder+HistGradientBoostingRegressor(log1p_target)",
        "training_data_version": data_version,
        "train_rows": int(len(train)), "test_rows": int(len(test)), "holdout_year": holdout_year,
        "metrics": metrics,
        "feature_schema": {"categorical": categorical_features, "numeric": numeric_features},
    }
    try:
        metadata["model_id"] = _register_model(metadata, model_name)
    except Exception:
        artifact_path.unlink(missing_ok=True)
        raise
    global _loaded_id, _loaded_artifact
    with _model_lock:
        _loaded_id, _loaded_artifact = metadata["model_id"], artifact
    return metadata


def train_cost_model(sample_per_year: int = 50_000) -> dict:
    """训练并激活已编码病例最终成本估算模型。"""
    return _train_model(
        model_name=MODEL_NAME, features=FEATURES,
        categorical_features=CATEGORICAL_FEATURES, numeric_features=NUMERIC_FEATURES,
        sample_per_year=sample_per_year,
    )


def train_future_cost_model(sample_per_year: int = 50_000) -> dict:
    """训练并激活仅使用入院前信息的未来病例成本模型。"""
    return _train_model(
        model_name=FUTURE_MODEL_NAME, features=PRE_ADMISSION_FEATURES,
        categorical_features=PRE_ADMISSION_CATEGORICAL_FEATURES,
        numeric_features=PRE_ADMISSION_NUMERIC_FEATURES,
        sample_per_year=sample_per_year,
    )


def active_model(model_name: str = MODEL_NAME) -> dict | None:
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 1 id,model_version,artifact_path,algorithm,training_data_version,train_rows,test_rows,"
            "holdout_year,metrics_json,trained_at,activated_at FROM dbo.ml_model "
            f"WHERE model_name={storage.PARAM} AND status='active' ORDER BY activated_at DESC,id DESC",
            (model_name,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        result = dict(zip([column[0] for column in cursor.description], row))
        result["metrics"] = json.loads(result.pop("metrics_json"))
        for key in ("trained_at", "activated_at"):
            if result.get(key):
                result[key] = result[key].isoformat()
        return result
    finally:
        conn.close()


def _load_active(model_name: str = MODEL_NAME) -> tuple[dict, dict]:
    import joblib

    record = active_model(model_name)
    if not record:
        raise FileNotFoundError("尚未训练并激活费用预测模型")
    global _loaded_id, _loaded_artifact
    with _model_lock:
        if _loaded_id != int(record["id"]) or _loaded_artifact is None:
            path = Path(record["artifact_path"])
            model_root = MODEL_DIR.resolve()
            path = path.resolve()
            if model_root not in path.parents:
                raise FileNotFoundError("已登记的费用模型路径超出模型目录")
            if not path.is_file():
                raise FileNotFoundError("已登记的费用模型文件不存在")
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=UserWarning, module=r"joblib\..*")
                _loaded_artifact = joblib.load(path)
            _loaded_id = int(record["id"])
        return record, _loaded_artifact


def _validated_features(values: dict, features: list[str] = FEATURES, categorical_features: list[str] = CATEGORICAL_FEATURES) -> dict:
    if not isinstance(values, dict):
        raise ValueError("features 必须是对象")
    unknown = sorted(set(values) - set(features))
    if unknown:
        raise ValueError(f"包含不支持的特征: {unknown}")
    result = {name: values.get(name) for name in features}
    for name in categorical_features:
        if result[name] is not None:
            result[name] = str(result[name]).strip()[:300] or None
    numeric_ranges = {
        "discharge_year": (2000, 2100), "length_of_stay": (0, 3650),
        "apr_severity_of_illness_code": (0, 4),
    }
    for name, (minimum, maximum) in numeric_ranges.items():
        if name not in features:
            continue
        if result[name] in (None, ""):
            result[name] = None
            continue
        try:
            value = float(result[name])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"特征 {name} 必须是数值") from exc
        if not minimum <= value <= maximum:
            raise ValueError(f"特征 {name} 必须在 {minimum} 到 {maximum} 之间")
        result[name] = value
    return result


def predict_cost(features: dict) -> dict:
    record, artifact = _load_active()
    clean = _validated_features(features)
    prediction = max(0.0, float(artifact["model"].predict(pd.DataFrame([clean], columns=FEATURES))[0]))
    mae = float(record["metrics"].get("mae") or 0)
    return {
        "predicted_total_cost": round(prediction, 2),
        "currency": "USD",
        "approximate_error_band": {
            "lower": round(max(0.0, prediction - mae), 2),
            "upper": round(prediction + mae, 2),
            "basis": "holdout_mae",
        },
        "model": {
            "id": int(record["id"]), "version": record["model_version"],
            "training_data_version": int(record["training_data_version"]),
            "holdout_year": int(record["holdout_year"]), "metrics": record["metrics"],
        },
        "scope": "基于已编码住院信息的最终成本估算，不是入院前预测或医疗建议。",
    }


def _future_growth_rate() -> tuple[float, int]:
    """以历史平均成本 CAGR 作为未来年度情景的默认调整率。"""
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT discharge_year,AVG(CAST(total_costs AS FLOAT)) FROM {storage.TABLE_NAME} "
            "WHERE discharge_year IS NOT NULL AND total_costs>0 "
            "GROUP BY discharge_year ORDER BY discharge_year"
        )
        rows = [(int(row[0]), float(row[1])) for row in cursor.fetchall() if row[1] and float(row[1]) > 0]
    finally:
        conn.close()
    if len(rows) < 2:
        raise ValueError("历史年度成本数据不足，无法生成未来费用情景")
    start_year, start_cost = rows[0]
    latest_year, latest_cost = rows[-1]
    rate = (latest_cost / start_cost) ** (1 / (latest_year - start_year)) - 1
    return max(-0.20, min(0.20, rate)), latest_year


def predict_future_cost(features: dict, forecast_year: int, annual_cost_growth_rate: float | None = None) -> dict:
    """根据入院前可知信息预测未来年度的病例最终成本。"""
    record, artifact = _load_active(FUTURE_MODEL_NAME)
    try:
        year = int(forecast_year)
    except (TypeError, ValueError) as exc:
        raise ValueError("forecast_year 必须是年份") from exc
    historical_rate, latest_year = _future_growth_rate()
    if not latest_year < year <= latest_year + 10:
        raise ValueError(f"forecast_year 必须在 {latest_year + 1} 到 {latest_year + 10} 之间")
    if annual_cost_growth_rate in (None, ""):
        growth_rate, source = historical_rate, "historical_cagr"
    else:
        try:
            growth_rate = float(annual_cost_growth_rate)
        except (TypeError, ValueError) as exc:
            raise ValueError("annual_cost_growth_rate 必须是数值") from exc
        if not -0.20 <= growth_rate <= 0.20:
            raise ValueError("annual_cost_growth_rate 必须在 -0.2 到 0.2 之间")
        source = "user_scenario"
    clean = _validated_features(features, PRE_ADMISSION_FEATURES, PRE_ADMISSION_CATEGORICAL_FEATURES)
    base_cost = max(0.0, float(artifact["model"].predict(pd.DataFrame([clean], columns=PRE_ADMISSION_FEATURES))[0]))
    factor = (1 + growth_rate) ** (year - latest_year)
    predicted = base_cost * factor
    mae = float(record["metrics"].get("mae") or 0) * factor
    return {
        "predicted_total_cost": round(predicted, 2), "currency": "USD",
        "forecast_year": year,
        "approximate_error_band": {"lower": round(max(0.0, predicted - mae), 2), "upper": round(predicted + mae, 2), "basis": "holdout_mae_adjusted"},
        "assumptions": {"latest_observed_year": latest_year, "annual_cost_growth_rate": round(growth_rate, 4), "growth_rate_source": source},
        "model": {"id": int(record["id"]), "version": record["model_version"], "holdout_year": int(record["holdout_year"]), "metrics": record["metrics"]},
        "scope": "基于入院前可知信息和年度成本增长情景的未来病例成本估算，不是报价、结算或医疗建议。",
    }


def _validate_rate(value, name: str, fallback: float) -> tuple[float, str]:
    if value in (None, ""):
        return fallback, "historical_cagr"
    try:
        rate = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是数值") from exc
    if not -0.20 <= rate <= 0.20:
        raise ValueError(f"{name} 必须在 -0.2 到 0.2 之间")
    return rate, "user_scenario"


def forecast_annual_budget(payload: dict) -> dict:
    """基于某医院或服务区域的历史病例量、次均成本 CAGR 生成年度预算情景。"""
    if not isinstance(payload, dict):
        raise ValueError("请求体必须是对象")
    scope_type = str(payload.get("scope_type") or "").strip()
    columns = {"service_area": "hospital_service_area", "hospital": "facility_name"}
    if scope_type not in columns:
        raise ValueError("scope_type 必须是 service_area 或 hospital")
    scope_value = str(payload.get("scope_value") or "").strip()
    if not 1 <= len(scope_value) <= 200:
        raise ValueError("scope_value 长度必须在 1 到 200 之间")
    conn = storage.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT discharge_year,COUNT_BIG(*),SUM(CAST(total_costs AS FLOAT)) FROM {storage.TABLE_NAME} "
            f"WHERE [{columns[scope_type]}]={storage.PARAM} AND discharge_year IS NOT NULL AND total_costs>0 "
            "GROUP BY discharge_year ORDER BY discharge_year",
            (scope_value,),
        )
        history = [{"year": int(row[0]), "case_count": int(row[1]), "total_cost": float(row[2])} for row in cursor.fetchall()]
    finally:
        conn.close()
    if len(history) < 2:
        raise ValueError("该范围至少需要两个有有效成本的历史年度，才能生成预算预测")
    latest = history[-1]
    first = history[0]
    try:
        target_year = int(payload.get("target_year"))
    except (TypeError, ValueError) as exc:
        raise ValueError("target_year 必须是年份") from exc
    if not latest["year"] < target_year <= latest["year"] + 10:
        raise ValueError(f"target_year 必须在 {latest['year'] + 1} 到 {latest['year'] + 10} 之间")
    span = latest["year"] - first["year"]
    historical_volume_rate = (latest["case_count"] / first["case_count"]) ** (1 / span) - 1
    first_average, latest_average = first["total_cost"] / first["case_count"], latest["total_cost"] / latest["case_count"]
    historical_cost_rate = (latest_average / first_average) ** (1 / span) - 1
    volume_rate, volume_source = _validate_rate(payload.get("annual_volume_growth_rate"), "annual_volume_growth_rate", historical_volume_rate)
    cost_rate, cost_source = _validate_rate(payload.get("annual_cost_growth_rate"), "annual_cost_growth_rate", historical_cost_rate)
    years_ahead = target_year - latest["year"]
    projected_cases = latest["case_count"] * (1 + volume_rate) ** years_ahead
    projected_avg_cost = latest_average * (1 + cost_rate) ** years_ahead
    return {
        "scope": {"type": scope_type, "value": scope_value}, "target_year": target_year, "currency": "USD",
        "forecast_total_cost": round(projected_cases * projected_avg_cost, 2),
        "forecast_case_count": round(projected_cases), "forecast_average_cost": round(projected_avg_cost, 2),
        "baseline": {"year": latest["year"], "case_count": latest["case_count"], "total_cost": round(latest["total_cost"], 2), "average_cost": round(latest_average, 2)},
        "assumptions": {"annual_volume_growth_rate": round(volume_rate, 4), "annual_cost_growth_rate": round(cost_rate, 4), "volume_rate_source": volume_source, "cost_rate_source": cost_source},
        "history": [{**row, "total_cost": round(row["total_cost"], 2), "average_cost": round(row["total_cost"] / row["case_count"], 2)} for row in history],
        "scope_note": "基于历史病例量与次均成本趋势的年度预算情景，不构成财务承诺或患者费用报价。",
    }


def cost_prediction_options(limit: int = 150) -> dict[str, list[dict]]:
    """返回模型训练时见过的编码，供费用表单搜索选择，避免在线全表聚合。"""
    limit = max(20, min(int(limit), 300))
    _record, artifact = _load_active(MODEL_NAME)
    try:
        transformer = artifact["model"].regressor_.named_steps["features"]
        encoder = transformer.named_transformers_["categorical"].named_steps["encoder"]
        categories = dict(zip(artifact["categorical_features"], encoder.categories_))
    except (AttributeError, KeyError) as exc:
        raise FileNotFoundError("已激活费用模型不包含可用的编码列表") from exc

    def options(feature: str) -> list[dict]:
        return [
            {"code": text, "description": ""}
            for value in categories.get(feature, [])
            if (text := str(value).strip()) and text != "UNKNOWN"
        ][:limit]

    return {
        "diagnosis": options("ccsr_diagnosis_code"),
        "procedure": options("ccsr_procedure_code"),
        "apr_drg": options("apr_drg_code"),
        "apr_mdc": options("apr_mdc_code"),
    }
