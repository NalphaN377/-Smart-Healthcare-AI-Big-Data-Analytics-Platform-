"""应用配置。

所有敏感配置只从环境变量或项目根目录 ``.env`` 读取，源码中不保存凭据。
项目一期使用 SQL Server；二期组件通过 feature flags 预留。
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - 最小离线环境兜底
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(BASE_DIR / ".env", override=False)

DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
BACKUP_DIR = DATA_DIR / "backup"
MODEL_DIR = DATA_DIR / "models"
DEFAULT_SOURCE_DATA = BASE_DIR.parent / "data" / "Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv"


def _bool_env(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


DB_CONFIG = {
    "backend": os.getenv("DB_BACKEND", "pymssql"),
    "driver": os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "1433")),
    "user": os.getenv("DB_USER", "sa"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "yiliaoBigData"),
    "encrypt": os.getenv("DB_ENCRYPT", "no"),
    "trust_server_certificate": _bool_env("DB_TRUST_SERVER_CERTIFICATE", True),
    "timeout": int(os.getenv("DB_TIMEOUT", "10")),
    "query_timeout": int(os.getenv("DB_QUERY_TIMEOUT", "60")),
}

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "50000"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "5000"))
SOURCE_DATA_PATH = Path(os.getenv("SOURCE_DATA_PATH", str(DEFAULT_SOURCE_DATA)))

LLM_CONFIG = {
    "provider": os.getenv("LLM_PROVIDER", "deepseek_anthropic"),
    "model": os.getenv("LLM_MODEL", "deepseek-v4-flash"),
    "api_key": os.getenv("DEEPSEEK_API_KEY", os.getenv("ANTHROPIC_API_KEY", "")),
    "base_url": os.getenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic"),
    "temperature": float(os.getenv("LLM_TEMPERATURE", "0.2")),
    "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "800")),
    "timeout": float(os.getenv("LLM_TIMEOUT", "25")),
}

FLASK_CONFIG = {
    "host": os.getenv("FLASK_HOST", "127.0.0.1"),
    "port": int(os.getenv("FLASK_PORT", "5000")),
    "debug": _bool_env("FLASK_DEBUG", False),
}

AUTH_CONFIG = {
    "secret_key": os.getenv("SECRET_KEY") or secrets.token_hex(32),
    "cookie_secure": _bool_env("SESSION_COOKIE_SECURE", False),
    "hours": int(os.getenv("SESSION_HOURS", "8")),
    "idle_minutes": int(os.getenv("SESSION_IDLE_MINUTES", "60")),
    "allowed_origins": [value.strip() for value in os.getenv(
        "CORS_ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
    ).split(",") if value.strip()],
}

FEATURES = {
    "llm_intent": _bool_env("FEATURE_LLM_INTENT", True),
    "redis_cache": _bool_env("FEATURE_REDIS_CACHE", False),
    "ml_analysis": _bool_env("FEATURE_ML_ANALYSIS", False),
    "distributed_engine": os.getenv("DISTRIBUTED_ENGINE", "pandas"),
    "local_llm": _bool_env("FEATURE_LOCAL_LLM", False),
}

REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "127.0.0.1"),
    "port": int(os.getenv("REDIS_PORT", "6379")),
    # Redis 使用数字数据库编号；项目名称通过 key_prefix 隔离。
    "db": int(os.getenv("REDIS_DB", "0")),
    "password": os.getenv("REDIS_PASSWORD") or None,
    "key_prefix": os.getenv("REDIS_KEY_PREFIX", "yiliaoBigData"),
    "default_ttl": int(os.getenv("REDIS_DEFAULT_TTL", "300")),
    "socket_timeout": float(os.getenv("REDIS_SOCKET_TIMEOUT", "1.5")),
}
