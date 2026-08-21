"""应用配置。

所有敏感配置只从环境变量或项目根目录 ``.env`` 读取，源码中不保存凭据。
项目一期使用 SQL Server；二期组件通过 feature flags 预留。
"""
from __future__ import annotations

import os
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
DEFAULT_SOURCE_DATA = BASE_DIR / "data" / "raw" / "Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv"


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

FEATURES = {
    "llm_intent": _bool_env("FEATURE_LLM_INTENT", False),
    "redis_cache": _bool_env("FEATURE_REDIS_CACHE", False),
    "ml_analysis": _bool_env("FEATURE_ML_ANALYSIS", False),
    "distributed_engine": os.getenv("DISTRIBUTED_ENGINE", "pandas"),
    "local_llm": _bool_env("FEATURE_LOCAL_LLM", False),
}
