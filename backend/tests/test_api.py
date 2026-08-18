def assert_success(response):
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["message"] is None
    assert "data" in payload
    assert "meta" in payload
    return payload


def test_health(client):
    payload = assert_success(client.get("/api/health"))
    assert payload["data"]["database"] == "ok"


def test_overview(client):
    payload = assert_success(client.get("/api/overview?year=2021"))
    assert payload["data"]["total_records"] == 4
    assert payload["meta"]["filters"] == {"year": 2021}


def test_diseases_top(client):
    payload = assert_success(client.get("/api/diseases/top?limit=5"))
    assert payload["data"][0]["diagnosis"] == "Influenza"


def test_hospitals_top(client):
    payload = assert_success(client.get("/api/hospitals/top?limit=5"))
    assert payload["data"][0]["hospital"] == "Example Medical Center"


def test_payments_distribution(client):
    payload = assert_success(client.get("/api/payments/distribution"))
    assert payload["data"][0]["percentage"] == 50.0


def test_cost_age_severity_and_trend_endpoints(client):
    for endpoint in (
        "/api/diseases/cost",
        "/api/hospitals/cost",
        "/api/age/distribution",
        "/api/age/cost",
        "/api/severity/distribution",
        "/api/trends/year",
    ):
        assert_success(client.get(endpoint))


def test_invalid_and_unknown_parameters_return_safe_error(client):
    for endpoint in ("/api/diseases/top?limit=0", "/api/overview?unknown=value"):
        response = client.get(endpoint)
        assert response.status_code == 400
        payload = response.get_json()
        assert payload["success"] is False
        assert payload["data"] is None
        assert "Traceback" not in payload["message"]


def test_ai_endpoint_is_reserved(client):
    response = client.post("/api/ai/query", json={"query": "老年患者费用最高的疾病？"})
    assert response.status_code == 501
    assert response.get_json()["message"] == "AI module reserved for Phase 2"

