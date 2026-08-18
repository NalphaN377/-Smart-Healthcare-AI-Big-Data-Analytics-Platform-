from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "medical_platform")
    MYSQL_USER = os.getenv("MYSQL_USER", "medical_user")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_CONNECT_TIMEOUT = int(os.getenv("MYSQL_CONNECT_TIMEOUT", "5"))
    MYSQL_READ_TIMEOUT = int(os.getenv("MYSQL_READ_TIMEOUT", "30"))
    MYSQL_WRITE_TIMEOUT = int(os.getenv("MYSQL_WRITE_TIMEOUT", "30"))
    REDIS_ENABLED = env_bool("REDIS_ENABLED", False)
    REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_CACHE_TTL = max(1, int(os.getenv("REDIS_CACHE_TTL", "300")))
    REDIS_SESSION_TTL = max(60, int(os.getenv("REDIS_SESSION_TTL", "86400")))
    DATA_QUALITY_METRICS_PATH = os.getenv(
        "DATA_QUALITY_METRICS_PATH",
        str(PROJECT_ROOT / "docs/data_quality_metrics.json"),
    )
    ML_MODEL_PATH = os.getenv(
        "ML_MODEL_PATH",
        str(PROJECT_ROOT / "backend/ml/artifacts/cost_model.joblib"),
    )
    ML_METADATA_PATH = os.getenv(
        "ML_METADATA_PATH",
        str(PROJECT_ROOT / "backend/ml/model_metadata.json"),
    )
    CORS_ORIGINS = [
        value.strip()
        for value in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if value.strip()
    ]
    JSON_SORT_KEYS = False
    MAX_QUERY_LIMIT = 100
    AI_PROVIDER = os.getenv("AI_PROVIDER", "openai_compatible")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
    LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    LLM_THINKING_MODE = os.getenv("LLM_THINKING_MODE", "disabled")
    AI_MAX_TURNS = min(20, max(1, int(os.getenv("AI_MAX_TURNS", "10"))))
    AI_MAX_SESSIONS = min(2_000, max(1, int(os.getenv("AI_MAX_SESSIONS", "500"))))
