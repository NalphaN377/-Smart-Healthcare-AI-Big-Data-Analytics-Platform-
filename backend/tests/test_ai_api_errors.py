from backend.app import create_app
from backend.app.ai.errors import ProviderFailure, ProviderTimeout
from backend.app.ai.schemas import ToolDecision
from backend.tests.conftest import FakeAnalyticsRepository


class ErrorProvider:
    configured = True

    def __init__(self, error):
        self.error = error

    @property
    def public_info(self):
        return {"name": "error_test", "model": "test"}

    def choose_tool(self, query, history, registry):
        raise self.error

    def summarize(self, query, result):
        raise AssertionError("summarize must not run")


class InvalidToolArgumentsProvider:
    configured = True

    @property
    def public_info(self):
        return {"name": "invalid_args_test", "model": "test"}

    def choose_tool(self, query, history, registry):
        return ToolDecision(tool="get_top_diseases", arguments={"limit": 51})

    def summarize(self, query, result):
        raise AssertionError("summarize must not run")


def make_client(provider):
    app = create_app(
        {
            "TESTING": True,
            "ANALYTICS_REPOSITORY": FakeAnalyticsRepository(),
            "AI_PROVIDER_INSTANCE": provider,
            "CORS_ORIGINS": ["http://localhost:5173"],
        }
    )
    return app.test_client()


def test_provider_timeout_returns_504_without_traceback():
    response = make_client(ErrorProvider(ProviderTimeout())).post(
        "/api/ai/query", json={"query": "总体住院情况如何？"}
    )
    assert response.status_code == 504
    assert response.get_json()["message"] == "LLM provider request timed out"
    assert "Traceback" not in str(response.get_json())


def test_provider_failure_returns_502():
    response = make_client(ErrorProvider(ProviderFailure())).post(
        "/api/ai/query", json={"query": "总体住院情况如何？"}
    )
    assert response.status_code == 502
    assert response.get_json()["message"] == "LLM provider request failed"


def test_llm_tool_arguments_are_revalidated_server_side():
    response = make_client(InvalidToolArgumentsProvider()).post(
        "/api/ai/query", json={"query": "疾病排名"}
    )
    assert response.status_code == 400
    assert response.get_json()["message"] == "AI tool validation failed"


def test_query_schema_rejects_extra_fields_and_excessive_length():
    client = make_client(ErrorProvider(AssertionError("provider must not run")))
    assert client.post(
        "/api/ai/query", json={"query": "概览", "sql": "SELECT *"}
    ).status_code == 400
    assert client.post("/api/ai/query", json={"query": "a" * 1001}).status_code == 400
