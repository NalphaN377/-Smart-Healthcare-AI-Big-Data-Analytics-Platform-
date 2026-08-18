from __future__ import annotations

import pytest

from backend.app import create_app


class FakeAnalyticsRepository:
    def ping(self):
        return True

    def overview(self, filters):
        return {
            "total_records": 4,
            "facility_count": 3,
            "avg_length_of_stay": 41.33,
            "avg_total_charges": 2233.5,
            "avg_total_costs": 1333.42,
            "emergency_ratio": 0.5,
        }

    def diseases_top(self, filters, limit):
        return [{"diagnosis": "Influenza", "record_count": 2}][:limit]

    def diseases_cost(self, filters, limit):
        return [
            {
                "diagnosis": "Influenza",
                "record_count": 2,
                "avg_total_charges": 1200.5,
                "avg_total_costs": 800.25,
            }
        ][:limit]

    def hospitals_top(self, filters, limit):
        return [{"hospital": "Example Medical Center", "record_count": 2}][:limit]

    def hospitals_cost(self, filters, limit):
        return [{"hospital": "Example Medical Center", "avg_total_charges": 1850.25}][:limit]

    def age_distribution(self, filters, limit):
        return [{"age_group": "18 to 29", "record_count": 1}][:limit]

    def age_cost(self, filters, limit):
        return [{"age_group": "18 to 29", "avg_total_charges": 1200.5}][:limit]

    def payment_distribution(self, filters, limit):
        return [{"payment_type": "Medicaid", "record_count": 2, "percentage": 50.0}][:limit]

    def severity_distribution(self, filters, limit):
        return [{"severity": "Moderate", "record_count": 2}][:limit]

    def yearly_trends(self, filters, limit):
        return [
            {"year": 2021, "record_count": 3},
            {"year": 2022, "record_count": 1},
        ][:limit]


@pytest.fixture()
def app():
    return create_app(
        {
            "TESTING": True,
            "ANALYTICS_REPOSITORY": FakeAnalyticsRepository(),
            "CORS_ORIGINS": ["http://localhost:5173"],
        }
    )


@pytest.fixture()
def client(app):
    return app.test_client()

