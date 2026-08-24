"""将自然语言问题解析为受控、可执行的数据分析意图。

优先使用大模型完成语义解析；模型不可用时使用本地规则。无论采用哪种方式，
最终结果都必须经过白名单校验，未知问题不会再被静默映射成默认年龄段查询。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Iterable, List

from config import LLM_CONFIG

logger = logging.getLogger(__name__)

DIMENSION_KEYWORDS = {
    "disease": ["疾病", "病种", "病类", "诊断类别", "疾病类别", "哪种病", "哪些病", "什么病", "病人"],
    "disease_code": ["疾病编码", "诊断编码", "ccsr编码", "ccsr code"],
    "age_group": ["年龄", "年龄段", "年龄组", "岁数", "老年", "老人", "儿童", "青少年"],
    "hospital": ["医院", "医疗机构", "院区", "机构"],
    "county": ["县", "郡", "county", "所在地区"],
    "service_area": ["服务区域", "服务区", "医疗服务区域", "片区"],
    "year": ["年份", "年度", "逐年", "历年", "每年", "时间趋势", "年变化"],
    "payment": ["支付方式", "支付类型", "医保", "保险", "付费方式", "付款方式"],
    "gender": ["性别", "男女", "男性女性", "男女性"],
    "admission_type": ["入院类型", "入院方式", "急诊入院", "择期入院"],
    "severity": ["严重程度", "病情严重", "病情等级", "严重等级"],
    "mortality_risk": ["死亡风险", "死亡危险", "病死风险"],
    "disposition": ["离院去向", "出院去向", "出院后去向", "转归"],
    "procedure": ["手术", "操作", "诊疗路径", "治疗路径", "主要手术"],
    "procedure_code": ["手术编码", "操作编码", "CCSR手术"],
    "race": ["种族", "人种"],
    "ethnicity": ["族裔", "民族背景"],
    "zip_area": ["邮编", "邮政区域"],
    "ed_indicator": ["急诊来源", "急诊标志", "急诊科"],
    "medical_surgical": ["医疗手术类型", "内外科", "医疗类", "手术类"],
    "apr_drg": ["APR DRG", "DRG分组", "DRG"],
    "apr_drg_code": ["DRG编码", "APR DRG编码"],
    "apr_mdc": ["APR MDC", "MDC类别", "主要疾病类别"],
    "apr_mdc_code": ["MDC编码", "APR MDC编码"],
    "payment_secondary": ["第二支付方式", "次要支付方式"],
    "payment_tertiary": ["第三支付方式"],
    "birth_weight_group": ["出生体重", "新生儿体重", "低出生体重"],
}

METRIC_KEYWORDS = {
    "avg_length_of_stay": ["住院时长", "住院日", "住院天数", "住多久", "住院时间", "平均住院", "住得最久", "住得最长", "住院更久", "住院较久", "住得更久"],
    "sum_total_charges": ["总费用", "费用总额", "总花费", "费用合计", "累计费用", "总收费"],
    "avg_total_charges": ["平均费用", "次均费用", "人均费用", "费用", "花费", "金额", "收费", "最贵", "费用最高"],
    "avg_total_costs": ["平均成本", "次均成本", "成本", "成本最高"],
    "sum_total_costs": ["总成本", "成本总额", "累计成本"],
    "count": ["数量", "人数", "人次", "住院量", "出院量", "例数", "病例数", "多少", "最多", "最少", "占比", "比例", "构成", "分布"],
    "record_share": ["记录占比", "病例占比", "构成比"],
    "charge_cost_spread": ["收费成本差额", "收费与成本差额", "账单成本差"],
    "charge_cost_spread_ratio": ["收费成本差额率", "账单成本差额率", "代理利润率", "利润率"],
    "cost_to_charge_ratio": ["成本收费比", "成本费用比"],
    "charge_to_cost_multiple": ["收费成本倍数", "账单成本倍数"],
    "charges_per_day": ["每日收费", "每住院日收费", "日均费用"],
    "costs_per_day": ["每日成本", "每住院日成本", "日均成本"],
    "procedure_rate": ["手术率", "操作率", "手术记录率"],
    "ed_rate": ["急诊来源占比", "急诊率", "ED占比"],
    "emergency_admission_rate": ["急诊入院占比", "急诊入院率"],
    "surgical_rate": ["手术类病例占比", "手术病例率"],
    "long_stay_rate": ["长期住院占比", "超长住院率", "30天以上"],
    "expired_disposition_rate": ["院内死亡占比", "死亡去向占比", "粗死亡率"],
    "cost_above_charge_rate": ["成本高于收费占比", "成本倒挂率"],
    "avg_birth_weight": ["平均出生体重"],
    "low_birth_weight_rate": ["低出生体重占比", "低体重儿比例"],
}

TOPIC_KEYWORDS = {
    "growth_ranking": ["增长最快", "增长最多", "增速最快", "增长率最高", "增长幅度最大"],
    "disease_trend": ["疾病趋势", "病种趋势", "疾病负担"],
    "complexity": ["病例复杂度", "病例组合", "严重程度资源"],
    "hospital_benchmark": ["病例组合校正", "医院成本指数", "医院效率指数", "校正后医院"],
    "pathway": ["诊疗路径", "疾病手术路径", "手术路径"],
    "emergency": ["急诊路径", "急诊和入院", "急诊分析"],
    "outcome": ["出院结局", "结局分析", "风险分层"],
    "payment": ["支付结构", "支付方式分析", "支付趋势"],
    "demographic": ["人口结构", "健康差异", "人群差异"],
    "maternal_newborn": ["妇产", "新生儿", "出生体重分析"],
    "operations": ["区域运营", "医院运营", "服务区域分析"],
    "regional_concentration": ["医院集中度", "区域集中度", "HHI"],
    "data_quality": ["数据质量", "异常检测", "标签漂移", "字段完整率"],
}

CHART_KEYWORDS = {
    "pie": ["饼图", "占比", "比例", "构成"],
    "line": ["折线图", "趋势", "变化", "逐年", "历年", "每年", "走势"],
    "bar": ["柱状图", "条形图", "对比", "比较", "排名", "排行", "top", "前几"],
}

ALLOWED_DIMENSIONS = frozenset(DIMENSION_KEYWORDS)
ALLOWED_METRICS = frozenset(METRIC_KEYWORDS)
ALLOWED_CHART_TYPES = {"bar", "pie", "line"}
ALLOWED_FILTERS = frozenset({"year", "year_from", "year_to", *DIMENSION_KEYWORDS})
ALLOWED_TOPICS = frozenset(TOPIC_KEYWORDS)
RATE_METRICS = frozenset({
    "record_share", "charge_cost_spread_ratio", "cost_to_charge_ratio",
    "procedure_rate", "ed_rate", "emergency_admission_rate", "surgical_rate",
    "long_stay_rate", "expired_disposition_rate", "cost_above_charge_rate",
    "low_birth_weight_rate",
})

DATA_TERMS = (
    "住院", "出院", "患者", "病人", "疾病", "病种", "诊断", "医院", "医疗机构", "费用", "收费",
    "成本", "利润", "差额", "年龄", "性别", "医保", "支付", "保险", "入院", "死亡风险", "离院", "医疗数据", "记录",
)
ANALYSIS_TERMS = (
    "多少", "哪些", "哪个", "哪类", "哪种", "最高", "最低", "最多", "最少", "平均", "总计", "合计",
    "占比", "比例", "分布", "趋势", "变化", "比较", "对比", "排名", "排行", "排序", "排一下", "统计", "分析", "情况",
)
PERSONAL_MEDICAL_PATTERNS = (
    r"我(得了|患有|是不是|应该|需要|能不能)", r"我的(症状|检查|报告|病情)", r"怎么(治疗|吃药|用药|诊断)",
    r"吃什么药", r"是否需要(手术|住院|吃药)", r"帮我诊断", r"处方", r"剂量",
)
GREETING_PATTERN = re.compile(r"^(你好|您好|嗨|hello|hi|在吗)[!！。,.，\s]*$", re.I)
CHINESE_NUMBERS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _contains_any(query: str, values: Iterable[str]) -> bool:
    lowered = query.lower()
    return any(value.lower() in lowered for value in values)


def _matched_keys(query: str, mapping: dict[str, list[str]]) -> list[tuple[str, int]]:
    """返回命中的 key 及最长命中词长度，减少“费用”覆盖“总费用”等歧义。"""
    lowered = query.lower()
    matches = []
    for key, keywords in mapping.items():
        lengths = [len(word) for word in keywords if word.lower() in lowered]
        if lengths:
            matches.append((key, max(lengths)))
    return sorted(matches, key=lambda item: item[1], reverse=True)


def detect_dimension(query: str) -> str | None:
    matches = _matched_keys(query, DIMENSION_KEYWORDS)
    if matches:
        return matches[0][0]
    if _contains_any(query, ("趋势", "走势", "同比", "逐年", "历年")):
        return "year"
    return None


def detect_metrics(query: str) -> List[str]:
    matches = _matched_keys(query, METRIC_KEYWORDS)
    matched = [key for key, _ in matches]
    # 具体口径优先，避免“总费用”同时落入平均费用。
    if "sum_total_charges" in matched and "avg_total_charges" in matched and not _contains_any(query, ("平均", "次均", "人均")):
        matched.remove("avg_total_charges")
    if "sum_total_costs" in matched and "avg_total_costs" in matched and not _contains_any(query, ("平均", "次均", "人均")):
        matched.remove("avg_total_costs")
    return matched


def detect_chart_type(query: str, metrics: List[str]) -> str:
    matches = _matched_keys(query, CHART_KEYWORDS)
    if matches:
        return matches[0][0]
    return "bar"


def detect_topic(query: str) -> str | None:
    matches = _matched_keys(query, TOPIC_KEYWORDS)
    return matches[0][0] if matches else None


def _top_limit(query: str) -> int:
    match = re.search(r"(?:top|前)\s*([一二两三四五六七八九十\d]{1,3})", query, flags=re.I)
    if not match:
        return 20
    token = match.group(1)
    if token.isdigit():
        value = int(token)
    elif token in CHINESE_NUMBERS:
        value = CHINESE_NUMBERS[token]
    elif "十" in token:
        left, right = token.split("十", 1)
        value = (CHINESE_NUMBERS.get(left, 1) * 10) + CHINESE_NUMBERS.get(right, 0)
    else:
        value = 20
    return min(max(value, 1), 50)


def _year_filters(query: str) -> dict:
    """提取单年份或显式年份范围；范围问题不能退化成首年等值过滤。"""
    years = [int(value) for value in re.findall(r"(?:19|20)\d{2}", query)]
    range_match = re.search(
        r"((?:19|20)\d{2})\s*(?:年)?\s*(?:到|至|—|–|-|~|～)\s*((?:19|20)\d{2})",
        query,
    )
    if range_match:
        start, end = (int(range_match.group(1)), int(range_match.group(2)))
        return {"year_from": min(start, end), "year_to": max(start, end)}
    if len(years) == 1:
        return {"year": years[0]}
    return {}


def _disease_filters(query: str) -> dict:
    """提取用户明示指定的英文疾病名称。

    例如“Septicemia类疾病”必须变成疾病筛选，不能对全部疾病做排名。
    中文疾病名容易与问句助词混淆，交由白名单校验后的LLM结果处理。
    """
    match = re.search(
        r"([A-Za-z][A-Za-z0-9 _/&,'().\-]{1,100}?)\s*(?:类疾病|疾病|患者|病例)",
        query,
        flags=re.I,
    )
    if not match:
        return {}
    value = re.sub(r"\s+", " ", match.group(1)).strip(" ,.;:")
    return {"disease": value} if value else {}


def _message(status: str, reason: str = "") -> str:
    if status == "medical_guidance":
        return (
            "我不能根据个人症状提供诊断、处方或治疗建议，因此不会生成数据图表。"
            "如有个人健康问题，请咨询专业医务人员；我可以协助分析本平台的脱敏住院统计数据。"
        )
    if status == "unsupported":
        return (
            "这个问题超出了当前脱敏住院数据的分析范围，因此暂不生成图表。"
            "你可以询问疾病、年龄、医院、区域、年份、支付方式等维度的住院量、住院日、费用或成本。"
        )
    if reason == "greeting":
        return "你好！我可以分析脱敏住院数据。你可以问：哪些疾病住院量最高，或各年份平均住院日如何变化？"
    if reason == "missing_metric":
        return "我已识别到分析对象，但还不确定你关注住院量、住院日、费用还是成本。请补充一个指标，暂不生成图表。"
    if reason == "missing_dimension":
        return "我已识别到指标，但还不确定要按疾病、年龄、医院、区域还是年份进行比较。请补充分析维度，暂不生成图表。"
    return "我还不能确定你的分析目标。请同时说明分析维度和指标，例如“按疾病比较平均住院费用”。"


def _base_intent(query: str, status: str, confidence: float, **extra) -> dict:
    return {
        "query": query,
        "status": status,
        "dimension": extra.get("dimension"),
        "metrics": extra.get("metrics", []),
        "chart_type": extra.get("chart_type", "bar"),
        "chart_requested": status == "ready",
        "limit": extra.get("limit", 20),
        "filters": extra.get("filters", {}),
        "sort_by": extra.get("sort_by"),
        "sort_order": extra.get("sort_order", "desc"),
        "confidence": round(max(0.0, min(float(confidence), 1.0)), 2),
        "message": extra.get("message", ""),
        "source": extra.get("source", "rules"),
        "topic": extra.get("topic"),
    }


def detect_intent(query: str) -> dict:
    """本地语义规则解析；不确定时明确澄清，绝不使用默认查询蒙混。"""
    query = re.sub(r"\s+", " ", str(query or "")).strip()
    if not query:
        return _base_intent(query, "clarification", 0.0, message=_message("clarification"))
    if any(re.search(pattern, query, re.I) for pattern in PERSONAL_MEDICAL_PATTERNS):
        return _base_intent(query, "unsupported", 0.98, message=_message("medical_guidance"))
    if GREETING_PATTERN.match(query):
        return _base_intent(query, "clarification", 0.95, message=_message("clarification", "greeting"))

    topic = detect_topic(query)
    if topic:
        if topic == "growth_ranking":
            dimension = detect_dimension(query)
            metrics = detect_metrics(query)
            if not dimension or not metrics:
                return _base_intent(
                    query, "clarification", 0.6, topic=topic, dimension=dimension,
                    metrics=metrics, message="请补充需要比较的对象和增长指标，例如“哪些疾病的总成本增长最快”。",
                )
            return _base_intent(
                query, "ready", 0.94, topic=topic, dimension=dimension,
                metrics=metrics, chart_type="bar", filters=_year_filters(query),
                sort_by="growth_pct", sort_order="desc", message="",
            )
        return _base_intent(
            query, "ready", 0.92, topic=topic, chart_type="line" if topic != "hospital_benchmark" else "bar",
            filters=_year_filters(query), message="",
        )

    dimension = detect_dimension(query)
    metrics = detect_metrics(query)
    primary_rate = next((metric for metric in metrics if metric in RATE_METRICS), None)
    if primary_rate and "count" not in metrics:
        metrics.append("count")
    has_domain = _contains_any(query, DATA_TERMS)
    has_analysis = _contains_any(query, ANALYSIS_TERMS)
    if not has_domain or (not dimension and not metrics and not has_analysis):
        return _base_intent(query, "unsupported", 0.9, message=_message("unsupported"))

    # 明确提到一个维度但省略指标时，“分布/哪些/排名”等自然表达可合理归为数量。
    if dimension and not metrics and _contains_any(query, ("分布", "哪些", "哪个", "哪类", "哪种", "排名", "排行", "情况", "统计")):
        metrics = ["count"]
    if metrics and not dimension:
        # “年度趋势”有稳定语义；其他场景不猜测分组维度。
        if _contains_any(query, ("趋势", "走势", "逐年", "历年", "每年", "同比")):
            dimension = "year"
        elif re.search(r"(?:19|20)\d{2}年?", query) and not _contains_any(query, ("按", "各", "不同", "比较", "对比")):
            dimension = "year"
        else:
            return _base_intent(
                query, "clarification", 0.55, metrics=metrics,
                message=_message("clarification", "missing_dimension"),
            )
    if dimension and not metrics:
        return _base_intent(
            query, "clarification", 0.55, dimension=dimension,
            message=_message("clarification", "missing_metric"),
        )
    if not dimension or not metrics:
        return _base_intent(query, "clarification", 0.35, message=_message("clarification"))

    limit = _top_limit(query)
    filters = {**_year_filters(query), **_disease_filters(query)}
    sort_by = primary_rate or (metrics[0] if _contains_any(query, ("最高", "最低", "最多", "最少", "最长", "最短", "排名", "排行", "排序", "排一下", "从高到低", "从低到高", "top", "前")) else None)
    sort_order = "asc" if _contains_any(query, ("最低", "最少", "最短", "从低到高", "升序")) else "desc"
    chart_type = detect_chart_type(query, metrics)
    if chart_type == "line" and dimension != "year" and "折线图" not in query:
        chart_type = "bar"
    intent = _base_intent(
        query,
        "ready",
        0.86 if has_analysis else 0.74,
        dimension=dimension,
        metrics=metrics,
        chart_type=chart_type,
        limit=limit,
        filters=filters,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    logger.info("规则意图识别结果: %s", intent)
    return intent


LLM_INTENT_SYSTEM_PROMPT = f"""你是医疗数据分析意图路由器，只输出一个 JSON 对象，不要输出解释或 Markdown。
可用数据仅为2021—2024年SPARCS脱敏住院出院记录。
dimension 仅可为：{','.join(sorted(ALLOWED_DIMENSIONS))}。
metrics 仅可为：{','.join(sorted(ALLOWED_METRICS))}。
topic 仅可为：{','.join(sorted(ALLOWED_TOPICS))}；专题问题可只返回topic，不强制dimension和metrics。
chart_type 仅可为 bar,pie,line。filters 仅允许：{','.join(sorted(ALLOWED_FILTERS))}。
status 仅可为 ready,clarification,unsupported。个人诊断、症状、治疗、处方问题必须 unsupported；不属于上述数据范围的问题必须 unsupported。
只有维度和指标都明确时才 ready；不要猜测缺失信息。自然同义表达要按语义理解，例如“住得最久”是 avg_length_of_stay，“最常见”是 count，“多少钱”是 avg_total_charges。
filters 中单年份使用 year；年份范围使用 year_from 和 year_to，例如“2021到2024年”必须输出 {{"year_from":2021,"year_to":2024}}，不能退化成 year=2021。
用户明确点名某种疾病时，filters 必须使用 disease 保留该疾病名，例如“Septicemia类疾病需要住多久”要输出 {{"disease":"Septicemia"}}。
JSON 字段固定为 status,topic,dimension,metrics,chart_type,limit,filters,sort_by,sort_order,confidence,message。
排名问题的 sort_by 必须是 metrics 中的指标，sort_order 仅为 asc 或 desc；confidence 为 0 到 1；非 ready 时用 message 给出简短中文引导。"""


def _history_text(history: list[dict] | None) -> str:
    clean = []
    for item in (history or [])[-6:]:
        role = "用户" if item.get("role") == "user" else "助手"
        content = str(item.get("content") or "").strip()[:300]
        if content:
            clean.append(f"{role}：{content}")
    return "\n".join(clean)


def _extract_json(text: str) -> dict:
    text = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.I | re.S)
    candidate = fenced.group(1) if fenced else text
    if not candidate.startswith("{"):
        match = re.search(r"\{.*\}", candidate, re.S)
        candidate = match.group(0) if match else candidate
    value = json.loads(candidate)
    if not isinstance(value, dict):
        raise ValueError("意图响应不是 JSON 对象")
    return value


def _validated_llm_intent(query: str, raw: dict) -> dict:
    status = str(raw.get("status") or "clarification").lower()
    if status not in {"ready", "clarification", "unsupported"}:
        status = "clarification"
    dimension = raw.get("dimension") if raw.get("dimension") in ALLOWED_DIMENSIONS else None
    topic = raw.get("topic") if raw.get("topic") in ALLOWED_TOPICS else detect_topic(query)
    metrics = [item for item in (raw.get("metrics") or []) if item in ALLOWED_METRICS]
    metrics = list(dict.fromkeys(metrics))[:4]
    chart_type = raw.get("chart_type") if raw.get("chart_type") in ALLOWED_CHART_TYPES else "bar"
    if chart_type == "line" and dimension != "year" and "折线图" not in query:
        chart_type = "bar"
    try:
        limit = min(max(int(raw.get("limit") or 20), 1), 50)
    except (TypeError, ValueError):
        limit = 20
    filters = {key: value for key, value in (raw.get("filters") or {}).items() if key in ALLOWED_FILTERS and value not in (None, "")}
    for year_key in ("year", "year_from", "year_to"):
        if year_key not in filters:
            continue
        try:
            filters[year_key] = int(filters[year_key])
        except (TypeError, ValueError):
            filters.pop(year_key)
    if "year_from" in filters and "year_to" in filters:
        start, end = filters["year_from"], filters["year_to"]
        filters["year_from"], filters["year_to"] = min(start, end), max(start, end)
        filters.pop("year", None)
    # 显式写在当前问题里的年份范围是硬约束。即使外部模型只返回了首年，
    # 也要用本地确定性解析结果覆盖，避免“2021到2024”退化为 year=2021。
    explicit_years = _year_filters(query)
    if "year_from" in explicit_years:
        filters.update(explicit_years)
        filters.pop("year", None)
    explicit_disease = _disease_filters(query)
    if explicit_disease:
        filters.update(explicit_disease)
    try:
        confidence = float(raw.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    sort_by = raw.get("sort_by") if raw.get("sort_by") in metrics else None
    sort_order = raw.get("sort_order") if raw.get("sort_order") in {"asc", "desc"} else "desc"

    if status == "ready" and (not topic and (not dimension or not metrics) or confidence < 0.55):
        status = "clarification"
    message = str(raw.get("message") or "").strip()[:300]
    if status != "ready" and not message:
        message = _message(status)
    return _base_intent(
        query, status, confidence, dimension=dimension, metrics=metrics, chart_type=chart_type,
        limit=limit, filters=filters, sort_by=sort_by, sort_order=sort_order, message=message, source="llm",
        topic=topic,
    )


def detect_intent_with_llm(query: str, history: list[dict] | None = None) -> dict:
    """使用大模型理解自然语言并强制白名单校验，异常时回退到本地规则。"""
    # 明确命中受控规则的问题直接执行。外部模型只负责补足规则无法确定的语义，
    # 不能把已确定的SQL分析意图降级成知识库回答或澄清问题。
    rule_intent = detect_intent(query)
    if rule_intent.get("status") == "ready":
        return rule_intent
    if not LLM_CONFIG.get("api_key"):
        return rule_intent
    try:
        from anthropic import Anthropic

        client = Anthropic(
            api_key=LLM_CONFIG["api_key"], base_url=LLM_CONFIG["base_url"], timeout=LLM_CONFIG["timeout"],
        )
        history_text = _history_text(history)
        prompt = (f"最近对话：\n{history_text}\n\n" if history_text else "") + f"当前用户问题：{query}"
        response = client.messages.create(
            model=LLM_CONFIG["model"], max_tokens=500, temperature=0,
            system=LLM_INTENT_SYSTEM_PROMPT, messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(getattr(block, "text", "") for block in response.content)
        intent = _validated_llm_intent(query, _extract_json(text))
        logger.info("LLM 意图识别结果: %s", intent)
        return intent
    except Exception as exc:  # 外部模型故障不能阻断基础数据查询
        logger.warning("LLM 意图识别失败，回退到本地规则: %s", exc.__class__.__name__)
        return rule_intent
