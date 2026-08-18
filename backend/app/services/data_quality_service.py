from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from threading import RLock


class DataQualityService:
    """Reads the precomputed quality snapshot; never scans the dataset in a request."""

    REQUIRED_KEYS = {
        "total_rows",
        "total_columns",
        "facility_count",
        "completeness_score",
        "validity_score",
        "consistency_score",
        "fields",
        "anomalies",
        "source",
        "generated_at",
    }

    def __init__(self, metrics_path: str | Path):
        self.metrics_path = Path(metrics_path)
        self._lock = RLock()
        self._cached: tuple[int, dict] | None = None

    def summary(self) -> dict:
        metrics = self._load()
        return {key: value for key, value in metrics.items() if key != "fields"}

    def fields(self) -> list[dict]:
        return self._load()["fields"]

    def _load(self) -> dict:
        try:
            modified_ns = self.metrics_path.stat().st_mtime_ns
        except OSError as error:
            raise FileNotFoundError("data quality metrics are unavailable") from error
        with self._lock:
            if self._cached and self._cached[0] == modified_ns:
                return deepcopy(self._cached[1])
            try:
                payload = json.loads(self.metrics_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError("data quality metrics are invalid") from error
            missing = self.REQUIRED_KEYS - set(payload)
            if missing or not isinstance(payload.get("fields"), list):
                raise ValueError("data quality metrics schema is invalid")
            self._cached = (modified_ns, payload)
            return deepcopy(payload)
