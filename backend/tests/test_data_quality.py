from __future__ import annotations

import json
from pathlib import Path

from backend.app import create_app
from backend.app.ai.provider import UnconfiguredProvider
from backend.app.services.data_quality_service import DataQualityService
from backend.tests.conftest import FakeAnalyticsRepository


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_real_quality_snapshot_matches_official_dataset():
    service = DataQualityService(PROJECT_ROOT / "docs/data_quality_metrics.json")
    summary = service.summary()
    assert summary["total_rows"] == 2_094_483
    assert summary["total_columns"] == 37
    assert summary["facility_count"] == 205
    assert summary["duplicate_rows_removed"] == 7_105
    assert summary["duplicate_rows_remaining"] == 0
    assert len(service.fields()) == 8


def test_quality_api_reads_snapshot_without_dataset_scan(tmp_path):
    metrics_path = tmp_path / "quality.json"
    metrics_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-08-18T00:00:00+00:00",
                "total_rows": 4,
                "total_columns": 37,
                "duplicate_rows_removed": 1,
                "duplicate_rows_remaining": 0,
                "facility_count": 3,
                "completeness_score": 99.0,
                "validity_score": 100.0,
                "consistency_score": 100.0,
                "fields": [
                    {"field": "severity", "missing_count": 1, "missing_rate": 25.0}
                ],
                "anomalies": {"negative_charges": 0},
                "source": {"processed_filename": "test.parquet"},
            }
        ),
        encoding="utf-8",
    )
    app = create_app(
        {
            "TESTING": True,
            "ANALYTICS_REPOSITORY": FakeAnalyticsRepository(),
            "AI_PROVIDER_INSTANCE": UnconfiguredProvider(),
            "DATA_QUALITY_METRICS_PATH": str(metrics_path),
            "CORS_ORIGINS": ["http://localhost:5173"],
        }
    )
    client = app.test_client()
    summary = client.get("/api/data-quality/summary")
    fields = client.get("/api/data-quality/fields")
    assert summary.status_code == 200
    assert summary.get_json()["data"]["total_rows"] == 4
    assert "fields" not in summary.get_json()["data"]
    assert fields.status_code == 200
    assert fields.get_json()["data"][0]["field"] == "severity"
    assert fields.get_json()["meta"]["snapshot"] is True


def test_quality_api_has_clear_unavailable_state(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "ANALYTICS_REPOSITORY": FakeAnalyticsRepository(),
            "AI_PROVIDER_INSTANCE": UnconfiguredProvider(),
            "DATA_QUALITY_METRICS_PATH": str(tmp_path / "missing.json"),
            "CORS_ORIGINS": ["http://localhost:5173"],
        }
    )
    response = app.test_client().get("/api/data-quality/summary")
    assert response.status_code == 503
    assert response.get_json()["message"] == (
        "Data quality metrics are unavailable; run the metrics generator"
    )
    assert "Traceback" not in str(response.get_json())
