from __future__ import annotations

import json
from pathlib import Path
from threading import RLock

import pandas as pd

from .schemas import CostPredictionRequest


DISCLAIMER = "仅用于数据分析和教学展示，不构成医疗建议、临床决策或费用结算依据。"


class ModelUnavailableError(RuntimeError):
    pass


class CostPredictionService:
    def __init__(self, model_path: str | Path, metadata_path: str | Path):
        self.model_path = Path(model_path)
        self.metadata_path = Path(metadata_path)
        self._lock = RLock()
        self._model = None
        self._metadata = None

    def status(self) -> dict:
        metadata = self._load_metadata(required=False)
        available = self.model_path.is_file() and metadata is not None
        return {
            "available": available,
            "model_version": metadata.get("model_version") if metadata else None,
            "target": metadata.get("target") if metadata else "total_costs",
            "features": metadata.get("features", []) if metadata else [],
            "feature_options": metadata.get("feature_options", {}) if metadata else {},
            "metrics": metadata.get("metrics", {}) if metadata else {},
            "sample_size": metadata.get("sample_size") if metadata else None,
            "trained_at": metadata.get("trained_at") if metadata else None,
            "disclaimer": DISCLAIMER,
        }

    def predict(self, request: CostPredictionRequest) -> dict:
        metadata = self._load_metadata(required=True)
        model = self._load_model()
        values = request.model_dump(mode="python")
        options = metadata.get("feature_options", {})
        diagnosis_options = set(options.get("diagnosis_code", []))
        if diagnosis_options and values["diagnosis_code"] not in diagnosis_options:
            raise ValueError("diagnosis_code is not present in the trained dataset")
        frame = pd.DataFrame([values], columns=metadata["features"])
        frame = frame.fillna("__MISSING__").astype(str)
        prediction = max(0.0, float(model.predict(frame)[0]))
        return {
            "predicted_cost": round(prediction, 2),
            "model_version": metadata["model_version"],
            "features_used": metadata["features"],
            "disclaimer": DISCLAIMER,
        }

    def _load_metadata(self, required: bool) -> dict | None:
        with self._lock:
            if self._metadata is not None:
                return self._metadata
            if not self.metadata_path.is_file():
                if required:
                    raise ModelUnavailableError("cost prediction model metadata is unavailable")
                return None
            try:
                metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                if required:
                    raise ModelUnavailableError("cost prediction model metadata is invalid") from error
                return None
            if not isinstance(metadata.get("features"), list) or not metadata.get("model_version"):
                if required:
                    raise ModelUnavailableError("cost prediction model metadata is invalid")
                return None
            self._metadata = metadata
            return metadata

    def _load_model(self):
        with self._lock:
            if self._model is not None:
                return self._model
            if not self.model_path.is_file():
                raise ModelUnavailableError("cost prediction model artifact is unavailable")
            try:
                import joblib

                self._model = joblib.load(self.model_path)
            except Exception as error:
                raise ModelUnavailableError("cost prediction model artifact could not be loaded") from error
            return self._model
