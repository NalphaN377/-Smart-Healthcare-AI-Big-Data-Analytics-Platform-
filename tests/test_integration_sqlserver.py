import os

import pytest

from app.data_layer import storage
from app.service_layer.analysis import aggregation
from app.service_layer.analysis.association import association_status, disease_procedure_associations
from app.ml.cost_model import active_model


pytestmark = pytest.mark.integration


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="set RUN_DB_TESTS=1 to test the configured SQL Server")
def test_imported_database_and_core_aggregations():
    ping = storage.ping()
    assert ping["database"] == "yiliaoBigData"

    overview = aggregation.overview()
    assert overview["summary"]["discharges"] == 8_508_252
    assert overview["summary"]["engine"] == "sqlserver_preaggregated"
    assert overview["summary"]["facilities"] > 100
    assert overview["diseases"]
    assert overview["ages"]

    payments = aggregation.payment_ratio(100)
    assert payments["total"] == 8_508_252
    assert sum(row["count"] for row in payments["rows"]) == payments["total"]
    assert sum(row["ratio"] for row in payments["rows"]) == pytest.approx(1.0, abs=1e-5)

    latest = storage.latest_ingestion()
    assert latest["status"] == "completed"
    assert latest["rows_inserted"] == 2_192_599
    assert latest["quality"]["overall"] >= 0.99

    trend = aggregation.year_trend()["rows"]
    assert {row["year"]: row["count"] for row in trend} == {
        2021: 2_094_418, 2022: 2_099_523, 2023: 2_121_712, 2024: 2_192_599,
    }

    association = disease_procedure_associations(limit=3, min_count=500, filters={"year": 2024})
    assert association["engine"] == "sqlserver_preaggregated"
    assert association["rows"]
    assert association_status()["association_data_version"] == storage.get_data_version()

    model = active_model()
    assert model and model["training_data_version"] == storage.get_data_version()
