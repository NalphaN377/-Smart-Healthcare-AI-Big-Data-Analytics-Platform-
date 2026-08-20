import os

import pytest

from app.data_layer import storage
from app.service_layer.analysis import aggregation


pytestmark = pytest.mark.integration


@pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="set RUN_DB_TESTS=1 to test the configured SQL Server")
def test_imported_database_and_core_aggregations():
    ping = storage.ping()
    assert ping["database"] == "yiliaoBigData"

    overview = aggregation.overview()
    assert overview["summary"]["discharges"] == 2_094_418
    assert overview["summary"]["facilities"] > 100
    assert overview["diseases"]
    assert overview["ages"]

    payments = aggregation.payment_ratio(100)
    assert payments["total"] == 2_094_418
    assert sum(row["count"] for row in payments["rows"]) == payments["total"]
    assert sum(row["ratio"] for row in payments["rows"]) == pytest.approx(1.0, abs=1e-5)

    latest = storage.latest_ingestion()
    assert latest["status"] == "completed"
    assert latest["rows_inserted"] == 2_094_418
    assert latest["quality"]["overall"] >= 0.99
