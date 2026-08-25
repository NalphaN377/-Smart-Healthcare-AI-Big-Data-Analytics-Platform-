"""轻量混合RAG：检索静态业务知识，并按需补充SQL动态元数据。

动态指标仍由结构化分析工具计算；本模块只向模型提供少量、可追溯的解释性上下文。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from config import BASE_DIR

KNOWLEDGE_PATH = Path(BASE_DIR) / "docs" / "ai_knowledge.json"
MAX_RESULTS = 3
MAX_CONTENT_CHARS = 700


@lru_cache(maxsize=1)
def _static_documents() -> tuple[dict, ...]:
    raw = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("AI知识库必须是文档数组")
    documents = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("id") or not item.get("content"):
            continue
        documents.append({**item, "source": "static_knowledge", "data_version": None})
    return tuple(documents)


def _ngrams(text: str, size: int = 2) -> set[str]:
    compact = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(text or "").lower())
    return {compact[index:index + size] for index in range(max(0, len(compact) - size + 1))}


def _score(query: str, document: dict) -> float:
    lowered = query.lower()
    score = 0.0
    for keyword in document.get("keywords") or []:
        keyword_text = str(keyword).lower()
        if keyword_text and keyword_text in lowered:
            score += 8.0 + min(len(keyword_text), 8) * 0.25
    title = str(document.get("title") or "").lower()
    if title and title in lowered:
        score += 10.0
    query_grams = _ngrams(query)
    document_grams = _ngrams(f"{title}{document.get('content', '')}")
    if query_grams and document_grams:
        score += len(query_grams & document_grams) / len(query_grams) * 5.0
    return score


def _dataset_profile() -> dict | None:
    """从预聚合表读取当前年份覆盖；数字不写入静态知识文件。"""
    try:
        from app.data_layer import storage
        from app.service_layer.analysis import aggregation

        data_version = storage.get_data_version()
        rows = aggregation.aggregate("year", ["count"], limit=50, filters={}).get("rows", [])
        years = sorted(
            [(int(row["dimension_value"]), int(row.get("count") or 0)) for row in rows],
            key=lambda item: item[0],
        )
        if not years:
            return None
        details = "；".join(f"{year}年{count:,}条" for year, count in years)
        return {
            "id": "dynamic_dataset_profile",
            "title": "当前数据覆盖与年度记录数",
            "content": f"当前数据版本为{data_version}，覆盖{years[0][0]}至{years[-1][0]}年。按出院年份统计：{details}。数字来自SQL预聚合结果。",
            "keywords": ["数据覆盖", "覆盖年份", "哪些年份", "当前数据", "年度记录", "出院人数", "出院人次", "住院量", "趋势"],
            "roles": ["patient", "doctor", "admin"],
            "source": "sql_metadata",
            "data_version": data_version,
        }
    except Exception:
        return None


def _model_profile() -> dict | None:
    try:
        from app.ml.cost_model import active_model

        model = active_model()
        if not model:
            return None
        metrics = model.get("metrics") or {}
        return {
            "id": "dynamic_cost_model",
            "title": "当前费用预测模型",
            "content": (
                f"当前模型版本{model['model_version']}，训练数据版本{model['training_data_version']}，"
                f"使用{model['train_rows']:,}条训练记录，并以{model['holdout_year']}年{model['test_rows']:,}条记录做时间外验证。"
                f"验证R²为{metrics.get('r2')}，MAE为{metrics.get('mae')}美元。"
            ),
            "keywords": ["费用预测", "成本预测", "模型版本", "训练数据", "准确率", "R2", "MAE"],
            "roles": ["patient", "doctor", "admin"],
            "source": "sql_model_registry",
            "data_version": model.get("training_data_version"),
        }
    except Exception:
        return None


def _quality_profile(role: str) -> dict | None:
    if role not in {"doctor", "admin"}:
        return None
    try:
        from app.data_layer import storage

        ingestion = storage.latest_ingestion() or {}
        quality = ingestion.get("quality") or {}
        if not ingestion:
            return None
        score = quality.get("overall")
        score_text = f"{float(score) * 100:.2f}%" if score is not None else "暂无综合评分"
        return {
            "id": "dynamic_quality_profile",
            "title": "当前数据质量与更新时间",
            "content": (
                f"最近数据接入状态为{ingestion.get('status') or '未知'}，写入{int(ingestion.get('rows_inserted') or 0):,}条，"
                f"丢弃{int(ingestion.get('rows_dropped') or 0):,}条，综合质量评分{score_text}，完成时间{ingestion.get('finished_at') or '未知'}。"
            ),
            "keywords": ["数据质量", "质量评分", "最近更新", "更新时间", "导入状态", "同步状态"],
            "roles": ["doctor", "admin"],
            "source": "sql_ingestion_metadata",
            "data_version": storage.get_data_version(),
        }
    except Exception:
        return None


def retrieve(query: str, role: str = "doctor", limit: int = MAX_RESULTS) -> list[dict]:
    """返回最多3个短片段；角色过滤先于打分，避免检索越权。"""
    role = role if role in {"patient", "doctor", "admin"} else "patient"
    documents = [dict(item) for item in _static_documents() if role in (item.get("roles") or [])]
    lowered = str(query or "").lower()
    dynamic_candidates = []
    if any(term in lowered for term in ("年份", "年度", "趋势", "当前数据", "数据覆盖", "出院人数", "出院人次", "住院量")):
        dynamic_candidates.append(_dataset_profile())
    if any(term in lowered for term in ("预测", "模型", "mae", "r2", "训练")):
        dynamic_candidates.append(_model_profile())
    if any(term in lowered for term in ("数据质量", "质量评分", "更新", "同步", "导入")):
        dynamic_candidates.append(_quality_profile(role))
    documents.extend(item for item in dynamic_candidates if item and role in item.get("roles", []))
    ranked = []
    for document in documents:
        score = _score(query, document)
        if score < 2.0:
            continue
        ranked.append({
            "id": document["id"],
            "title": document.get("title") or document["id"],
            "content": str(document.get("content") or "")[:MAX_CONTENT_CHARS],
            "source": document.get("source") or "knowledge",
            "data_version": document.get("data_version"),
            "score": round(score, 3),
        })
    ranked.sort(key=lambda item: (-item["score"], item["id"]))
    return ranked[:max(1, min(int(limit), MAX_RESULTS))]


def compact_context(documents: list[dict]) -> str:
    return "\n".join(
        f"[{item['title']}] {str(item.get('content') or '')[:MAX_CONTENT_CHARS]}"
        for item in documents[:MAX_RESULTS]
    )
