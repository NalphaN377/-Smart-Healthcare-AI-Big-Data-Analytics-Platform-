"""意图识别：将用户自然语言解析为结构化查询意图。

对应文档功能「智能工具调用」：
根据解析后的用户意图，自动匹配并调用对应的分析 API。

实现策略：
- 默认走「规则匹配」：基于关键词词典，零依赖、可离线、结果可预期。
- 二期可切换「LLM 语义识别」：用 LangChain 做模糊查询、多维意图、术语联想，
  将准确率提升至 90% 以上。
"""
import logging
import re
from typing import List

logger = logging.getLogger(__name__)

# 维度关键词 -> 维度 key（与 service_layer.analysis.aggregation.DIMENSIONS 对应）
DIMENSION_KEYWORDS = {
    "disease": ["疾病", "病种", "诊断", "什么病"],
    "age_group": ["年龄", "年龄段", "年龄段分布"],
    "hospital": ["医院", "医疗机构", "哪个医院"],
    "county": ["县", "地区", "郡"],
    "service_area": ["服务区域", "区域"],
    "year": ["年份", "年度", "趋势", "哪一年", "逐年"],
    "payment": ["支付方式", "医保", "付费", "支付"],
    "gender": ["性别"],
    "admission_type": ["入院类型", "入院方式"],
    "severity": ["严重程度", "病情严重"],
}

# 指标关键词 -> 指标 key
METRIC_KEYWORDS = {
    "avg_length_of_stay": ["住院时长", "住院天数", "住院时间", "平均住院"],
    "sum_total_charges": ["总费用", "费用总额", "总花费"],
    "avg_total_charges": ["费用", "花费", "金额", "收费", "平均费用"],
    "avg_total_costs": ["成本", "平均成本"],
    "count": ["数量", "人数", "住院量", "例数", "多少", "占比", "比例"],
}

# 图表类型关键词
CHART_KEYWORDS = {
    "pie": ["占比", "比例", "分布", "构成"],
    "line": ["趋势", "变化", "逐年", "年份"],
}


def detect_dimension(query: str) -> str:
    """规则匹配维度，默认 age_group。"""
    for dim, keywords in DIMENSION_KEYWORDS.items():
        if any(k in query for k in keywords):
            return dim
    return "age_group"


def detect_metrics(query: str) -> List[str]:
    """规则匹配指标，默认 count + 平均住院时长。"""
    matched = []
    for metric, keywords in METRIC_KEYWORDS.items():
        if any(k in query for k in keywords):
            matched.append(metric)
    if not matched:
        # 用户没明确问指标时，默认给「住院量 + 平均住院时长」
        matched = ["count", "avg_length_of_stay"]
    return matched


def detect_chart_type(query: str, metrics: List[str]) -> str:
    """规则匹配图表类型。"""
    for chart, keywords in CHART_KEYWORDS.items():
        if any(k in query for k in keywords):
            return chart
    return "bar"


def detect_intent(query: str) -> dict:
    """解析自然语言查询为结构化意图。

    Returns:
        {
            "query": 原文,
            "dimension": 维度 key,
            "metrics": [指标 key, ...],
            "chart_type": bar / pie / line,
        }
    """
    dimension = detect_dimension(query)
    metrics = detect_metrics(query)
    chart_type = detect_chart_type(query, metrics)
    top_match = re.search(r"(?:top|前)\s*(\d{1,2})", query, flags=re.I)
    year_match = re.search(r"(?:19|20)\d{2}", query)
    limit = min(max(int(top_match.group(1)), 1), 50) if top_match else 20
    filters = {"year": int(year_match.group())} if year_match else {}
    intent = {
        "query": query,
        "dimension": dimension,
        "metrics": metrics,
        "chart_type": chart_type,
        "limit": limit,
        "filters": filters,
        "confidence": 0.92 if any(k in query for values in DIMENSION_KEYWORDS.values() for k in values) else 0.65,
    }
    logger.info("意图识别结果: %s", intent)
    return intent


def detect_intent_with_llm(query: str) -> dict:
    """LLM 语义意图识别（二期）：用大模型做模糊/多维意图识别。

    TODO: 二期实现 —— 构造 few-shot prompt 让 LLM 输出结构化 JSON，
    覆盖「模糊查询、多维度查询、医疗术语联想」场景。
    """
    # 占位：当前回退到规则识别，保证系统可用
    return detect_intent(query)
