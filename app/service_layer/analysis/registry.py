"""分析维度与指标注册表。

注册表是 SQL 白名单、角色权限、最小样本量、展示单位和口径说明的唯一事实源。
所有表达式均为源码内受信任常量，用户输入只能作为参数值进入查询。
"""
from __future__ import annotations

from dataclasses import dataclass

ALL_ROLES = frozenset({"patient", "doctor", "admin"})
CLINICAL_ROLES = frozenset({"doctor", "admin"})
ADMIN_ONLY = frozenset({"admin"})


@dataclass(frozen=True)
class DimensionSpec:
    key: str
    label: str
    expression: str
    roles: frozenset[str] = CLINICAL_ROLES
    min_count: int = 1
    sensitive: bool = False
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    expression: str
    roles: frozenset[str]
    unit: str = ""
    description: str = ""
    disclaimer: str = ""


AGE_GROUP_SQL = """CASE
 WHEN age_group IN (N'0 to 17',N'0-17') THEN N'0-17'
 WHEN age_group IN (N'18 to 29',N'18-29') THEN N'18-29'
 WHEN age_group IN (N'30 to 49',N'30-49') THEN N'30-49'
 WHEN age_group IN (N'50 to 69',N'50-69') THEN N'50-69'
 WHEN age_group IN (N'70 or Older',N'70+',N'70 and Older') THEN N'70+'
 ELSE COALESCE(NULLIF(LTRIM(RTRIM(age_group)),N''),N'(未标注)') END"""

SERVICE_AREA_SQL = """CASE
 WHEN hospital_service_area IN (N'Capital/Adirond',N'Capital/Adirondacks') THEN N'Capital/Adirondacks'
 ELSE COALESCE(NULLIF(LTRIM(RTRIM(hospital_service_area)),N''),N'(未标注)') END"""

HOSPITAL_SQL = "UPPER(COALESCE(NULLIF(LTRIM(RTRIM(REPLACE(facility_name,N'`',N''''))),N''),N'(未标注)'))"

BIRTH_WEIGHT_GROUP_SQL = """CASE
 WHEN TRY_CONVERT(INT,NULLIF(birth_weight,N'')) IS NULL THEN N'(不适用或未标注)'
 WHEN TRY_CONVERT(INT,birth_weight)<1500 THEN N'<1500g'
 WHEN TRY_CONVERT(INT,birth_weight)<2500 THEN N'1500-2499g'
 WHEN TRY_CONVERT(INT,birth_weight)<4000 THEN N'2500-3999g'
 ELSE N'>=4000g' END"""

DIMENSIONS: dict[str, DimensionSpec] = {
    "disease": DimensionSpec("disease", "疾病", "UPPER(COALESCE(NULLIF(LTRIM(RTRIM(ccsr_diagnosis_description)),N''),N'(未标注)'))", ALL_ROLES),
    "disease_code": DimensionSpec("disease_code", "疾病编码", "COALESCE(NULLIF(LTRIM(RTRIM(ccsr_diagnosis_code)),N''),N'(未标注)')"),
    "procedure": DimensionSpec("procedure", "手术/操作", "UPPER(COALESCE(NULLIF(LTRIM(RTRIM(ccsr_procedure_description)),N''),N'(未标注)'))"),
    "procedure_code": DimensionSpec("procedure_code", "手术/操作编码", "COALESCE(NULLIF(LTRIM(RTRIM(ccsr_procedure_code)),N''),N'(未标注)')"),
    "age_group": DimensionSpec("age_group", "年龄段", AGE_GROUP_SQL, CLINICAL_ROLES),
    "hospital": DimensionSpec("hospital", "医疗机构", HOSPITAL_SQL, CLINICAL_ROLES, 30),
    "county": DimensionSpec("county", "地区", "COALESCE(NULLIF(LTRIM(RTRIM(hospital_county)),N''),N'(未标注)')"),
    "service_area": DimensionSpec("service_area", "服务区域", SERVICE_AREA_SQL, ALL_ROLES),
    "year": DimensionSpec("year", "出院年份", "discharge_year", ALL_ROLES),
    "payment": DimensionSpec("payment", "主要支付方式", "COALESCE(NULLIF(LTRIM(RTRIM(payment_typology_1)),N''),N'(未标注)')"),
    "payment_secondary": DimensionSpec("payment_secondary", "第二支付方式", "COALESCE(NULLIF(LTRIM(RTRIM(payment_typology_2)),N''),N'(未标注)')", ADMIN_ONLY),
    "payment_tertiary": DimensionSpec("payment_tertiary", "第三支付方式", "COALESCE(NULLIF(LTRIM(RTRIM(payment_typology_3)),N''),N'(未标注)')", ADMIN_ONLY),
    "gender": DimensionSpec("gender", "性别", "COALESCE(NULLIF(LTRIM(RTRIM(gender)),N''),N'(未标注)')", CLINICAL_ROLES, 30, True),
    "race": DimensionSpec("race", "种族", "COALESCE(NULLIF(LTRIM(RTRIM(race)),N''),N'(未标注)')", CLINICAL_ROLES, 30, True),
    "ethnicity": DimensionSpec("ethnicity", "族裔", "COALESCE(NULLIF(LTRIM(RTRIM(ethnicity)),N''),N'(未标注)')", CLINICAL_ROLES, 30, True),
    "zip_area": DimensionSpec("zip_area", "邮编前三位", "COALESCE(NULLIF(LTRIM(RTRIM(zip_code_3)),N''),N'(未标注)')", CLINICAL_ROLES, 30, True),
    "admission_type": DimensionSpec("admission_type", "入院类型", "COALESCE(NULLIF(LTRIM(RTRIM(type_of_admission)),N''),N'(未标注)')"),
    "ed_indicator": DimensionSpec("ed_indicator", "急诊来源", "COALESCE(NULLIF(LTRIM(RTRIM(emergency_department_indicator)),N''),N'(未标注)')"),
    "severity": DimensionSpec("severity", "病情严重程度", "COALESCE(NULLIF(LTRIM(RTRIM(apr_severity_of_illness_desc)),N''),N'(未标注)')"),
    "mortality_risk": DimensionSpec("mortality_risk", "死亡风险", "COALESCE(NULLIF(LTRIM(RTRIM(apr_risk_of_mortality)),N''),N'(未标注)')"),
    "disposition": DimensionSpec("disposition", "离院去向", "COALESCE(NULLIF(LTRIM(RTRIM(patient_disposition)),N''),N'(未标注)')"),
    "medical_surgical": DimensionSpec("medical_surgical", "医疗/手术类型", "COALESCE(NULLIF(LTRIM(RTRIM(apr_medical_surgical_desc)),N''),N'(未标注)')"),
    "apr_drg": DimensionSpec("apr_drg", "APR DRG", "COALESCE(NULLIF(LTRIM(RTRIM(apr_drg_description)),N''),N'(未标注)')"),
    "apr_drg_code": DimensionSpec("apr_drg_code", "APR DRG编码", "COALESCE(NULLIF(LTRIM(RTRIM(apr_drg_code)),N''),N'(未标注)')"),
    "apr_mdc": DimensionSpec("apr_mdc", "APR MDC", "COALESCE(NULLIF(LTRIM(RTRIM(apr_mdc_description)),N''),N'(未标注)')"),
    "apr_mdc_code": DimensionSpec("apr_mdc_code", "APR MDC编码", "COALESCE(NULLIF(LTRIM(RTRIM(apr_mdc_code)),N''),N'(未标注)')"),
    "birth_weight_group": DimensionSpec("birth_weight_group", "出生体重组", BIRTH_WEIGHT_GROUP_SQL, CLINICAL_ROLES, 30, True),
}


METRICS: dict[str, MetricSpec] = {
    "count": MetricSpec("count", "住院量", "COUNT_BIG(*)", ALL_ROLES, "条", "住院出院记录数，不是去重患者人数"),
    "record_share": MetricSpec("record_share", "记录占比", "COUNT_BIG(*)*100.0/NULLIF(SUM(COUNT_BIG(*)) OVER(),0)", ALL_ROLES, "%"),
    "avg_length_of_stay": MetricSpec("avg_length_of_stay", "平均住院日", "AVG(CAST(length_of_stay AS FLOAT))", ALL_ROLES, "天"),
    "avg_total_charges": MetricSpec("avg_total_charges", "次均账单费用", "AVG(CAST(total_charges AS FLOAT))", ALL_ROLES, "USD", "名义账单收费金额"),
    "sum_total_charges": MetricSpec("sum_total_charges", "账单费用总额", "SUM(CAST(total_charges AS FLOAT))", CLINICAL_ROLES, "USD"),
    "avg_total_costs": MetricSpec("avg_total_costs", "次均实际成本", "AVG(CAST(total_costs AS FLOAT))", CLINICAL_ROLES, "USD"),
    "sum_total_costs": MetricSpec("sum_total_costs", "实际成本总额", "SUM(CAST(total_costs AS FLOAT))", CLINICAL_ROLES, "USD"),
    "charge_cost_spread": MetricSpec("charge_cost_spread", "收费—成本差额", "SUM(CAST(total_charges AS FLOAT))-SUM(CAST(total_costs AS FLOAT))", ADMIN_ONLY, "USD", disclaimer="收费不是净收入，该指标不代表利润"),
    "charge_cost_spread_ratio": MetricSpec("charge_cost_spread_ratio", "收费成本差额率", "(SUM(CAST(total_charges AS FLOAT))-SUM(CAST(total_costs AS FLOAT)))*100.0/NULLIF(SUM(CAST(total_charges AS FLOAT)),0)", ADMIN_ONLY, "%", disclaimer="代理指标，不是医院利润率"),
    "cost_to_charge_ratio": MetricSpec("cost_to_charge_ratio", "成本收费比", "SUM(CAST(total_costs AS FLOAT))*100.0/NULLIF(SUM(CAST(total_charges AS FLOAT)),0)", ADMIN_ONLY, "%", disclaimer="收费不是实际回款"),
    "charge_to_cost_multiple": MetricSpec("charge_to_cost_multiple", "收费成本倍数", "SUM(CAST(total_charges AS FLOAT))/NULLIF(SUM(CAST(total_costs AS FLOAT)),0)", ADMIN_ONLY, "倍", disclaimer="收费不是实际回款"),
    "charges_per_day": MetricSpec("charges_per_day", "每住院日收费", "SUM(CAST(total_charges AS FLOAT))/NULLIF(SUM(CAST(length_of_stay AS FLOAT)),0)", CLINICAL_ROLES, "USD/天"),
    "costs_per_day": MetricSpec("costs_per_day", "每住院日成本", "SUM(CAST(total_costs AS FLOAT))/NULLIF(SUM(CAST(length_of_stay AS FLOAT)),0)", CLINICAL_ROLES, "USD/天"),
    "procedure_rate": MetricSpec("procedure_rate", "手术/操作记录率", "SUM(CASE WHEN NULLIF(LTRIM(RTRIM(ccsr_procedure_code)),N'') IS NOT NULL THEN 1.0 ELSE 0 END)*100.0/NULLIF(COUNT_BIG(*),0)", CLINICAL_ROLES, "%"),
    "ed_rate": MetricSpec("ed_rate", "急诊来源占比", "SUM(CASE WHEN emergency_department_indicator=N'Y' THEN 1.0 ELSE 0 END)*100.0/NULLIF(COUNT_BIG(*),0)", CLINICAL_ROLES, "%"),
    "emergency_admission_rate": MetricSpec("emergency_admission_rate", "急诊入院占比", "SUM(CASE WHEN type_of_admission=N'Emergency' THEN 1.0 ELSE 0 END)*100.0/NULLIF(COUNT_BIG(*),0)", CLINICAL_ROLES, "%"),
    "surgical_rate": MetricSpec("surgical_rate", "手术类病例占比", "SUM(CASE WHEN apr_medical_surgical_desc=N'Surgical' THEN 1.0 ELSE 0 END)*100.0/NULLIF(COUNT_BIG(*),0)", CLINICAL_ROLES, "%"),
    "long_stay_rate": MetricSpec("long_stay_rate", "30天及以上住院占比", "SUM(CASE WHEN length_of_stay>=30 THEN 1.0 ELSE 0 END)*100.0/NULLIF(COUNT_BIG(*),0)", CLINICAL_ROLES, "%"),
    "expired_disposition_rate": MetricSpec("expired_disposition_rate", "院内死亡去向占比", "SUM(CASE WHEN patient_disposition LIKE N'%Expired%' THEN 1.0 ELSE 0 END)*100.0/NULLIF(COUNT_BIG(*),0)", CLINICAL_ROLES, "%", disclaimer="粗结局比例，不能直接用于医院质量排名"),
    "cost_above_charge_rate": MetricSpec("cost_above_charge_rate", "成本高于收费记录占比", "SUM(CASE WHEN total_costs>total_charges THEN 1.0 ELSE 0 END)*100.0/NULLIF(COUNT_BIG(*),0)", ADMIN_ONLY, "%"),
    "avg_birth_weight": MetricSpec("avg_birth_weight", "平均出生体重", "AVG(TRY_CONVERT(FLOAT,NULLIF(birth_weight,N'')))", CLINICAL_ROLES, "g"),
    "low_birth_weight_rate": MetricSpec("low_birth_weight_rate", "低出生体重占比", "SUM(CASE WHEN TRY_CONVERT(INT,NULLIF(birth_weight,N''))<2500 THEN 1.0 ELSE 0 END)*100.0/NULLIF(COUNT_BIG(NULLIF(birth_weight,N'')),0)", CLINICAL_ROLES, "%"),
}


FILTERS: dict[str, tuple[str, type]] = {
    "year": ("discharge_year", int),
    "year_from": ("discharge_year", int),
    "year_to": ("discharge_year", int),
    **{key: (spec.expression, str) for key, spec in DIMENSIONS.items() if key != "year"},
}


def dimensions_for(role: str) -> dict[str, DimensionSpec]:
    return {key: spec for key, spec in DIMENSIONS.items() if role in spec.roles}


def metrics_for(role: str) -> dict[str, MetricSpec]:
    return {key: spec for key, spec in METRICS.items() if role in spec.roles}


def require_dimension(key: str, role: str) -> DimensionSpec:
    spec = DIMENSIONS.get(key)
    if not spec:
        raise ValueError(f"未知维度: {key}")
    if role not in spec.roles:
        raise PermissionError(f"当前角色无权访问维度“{spec.label}”")
    return spec


def require_metric(key: str, role: str) -> MetricSpec:
    spec = METRICS.get(key)
    if not spec:
        raise ValueError(f"未知指标: {key}")
    if role not in spec.roles:
        raise PermissionError(f"当前角色无权访问指标“{spec.label}”")
    return spec


def normalize_filter_value(key: str, value):
    """把查询值归一化到跨年度统一口径。"""
    if not isinstance(value, str):
        return value
    clean = value.strip()
    if key == "age_group":
        return {
            "0 to 17": "0-17", "18 to 29": "18-29", "30 to 49": "30-49",
            "50 to 69": "50-69", "70 or Older": "70+", "70 and Older": "70+",
        }.get(clean, clean)
    if key == "service_area" and clean == "Capital/Adirond":
        return "Capital/Adirondacks"
    if key in {"disease", "procedure", "hospital"}:
        return clean.replace("`", "'").upper() if key == "hospital" else clean.upper()
    return clean
