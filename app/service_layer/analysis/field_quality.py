"""字段级数据质量矩阵。

一次扫描按年度计算全部入库字段，避免对大表逐字段发起查询。条件适用字段单独
标识为覆盖率，不把业务上合理的空值误判为质量缺失。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.data_layer import storage
from app.service_layer.analysis import aggregation


@dataclass(frozen=True)
class FieldSpec:
    field: str
    label: str
    domain: str
    valid: str | None = None
    applicable: str | None = None
    conditional: bool = False


def _present(field: str) -> str:
    return f"NULLIF(LTRIM(RTRIM(CONVERT(NVARCHAR(4000),[{field}]))),N'') IS NOT NULL"


_year = datetime.utcnow().year
FIELDS = (
    FieldSpec("hospital_service_area", "服务区域", "机构信息"),
    FieldSpec("hospital_county", "医院所在县", "机构信息"),
    FieldSpec("operating_certificate_number", "运营许可证号", "机构信息", "TRY_CONVERT(BIGINT,operating_certificate_number) IS NOT NULL"),
    FieldSpec("permanent_facility_id", "永久机构ID", "机构信息", "TRY_CONVERT(BIGINT,permanent_facility_id) IS NOT NULL"),
    FieldSpec("facility_name", "医疗机构名称", "机构信息"),
    FieldSpec("age_group", "年龄段", "人口特征", "age_group IN (N'0 to 17',N'0-17',N'18 to 29',N'18-29',N'30 to 49',N'30-49',N'50 to 69',N'50-69',N'70 or Older',N'70+',N'70 and Older')"),
    FieldSpec("zip_code_3", "邮编前三位", "人口特征", "LEN(LTRIM(RTRIM(zip_code_3)))=3 AND zip_code_3 NOT LIKE N'%[^0-9]%'"),
    FieldSpec("gender", "性别", "人口特征", "gender IN (N'M',N'F',N'U')"),
    FieldSpec("race", "种族", "人口特征"),
    FieldSpec("ethnicity", "族裔", "人口特征"),
    FieldSpec("length_of_stay", "住院日", "就诊过程", "TRY_CONVERT(INT,length_of_stay) BETWEEN 0 AND 3650"),
    FieldSpec("type_of_admission", "入院类型", "就诊过程"),
    FieldSpec("patient_disposition", "离院去向", "就诊过程"),
    FieldSpec("discharge_year", "出院年份", "就诊过程", f"TRY_CONVERT(INT,discharge_year) BETWEEN 2000 AND {_year}"),
    FieldSpec("ccsr_diagnosis_code", "CCSR诊断编码", "诊断分组"),
    FieldSpec("ccsr_diagnosis_description", "CCSR诊断描述", "诊断分组"),
    FieldSpec("ccsr_procedure_code", "CCSR手术/操作编码", "手术操作", conditional=True),
    FieldSpec("ccsr_procedure_description", "CCSR手术/操作描述", "手术操作", conditional=True),
    FieldSpec("apr_drg_code", "APR DRG编码", "临床分组"),
    FieldSpec("apr_drg_description", "APR DRG描述", "临床分组"),
    FieldSpec("apr_mdc_code", "APR MDC编码", "临床分组"),
    FieldSpec("apr_mdc_description", "APR MDC描述", "临床分组"),
    FieldSpec("apr_severity_of_illness_code", "APR严重程度编码", "临床分组", "TRY_CONVERT(INT,apr_severity_of_illness_code) BETWEEN 1 AND 4"),
    FieldSpec("apr_severity_of_illness_desc", "APR严重程度描述", "临床分组"),
    FieldSpec("apr_risk_of_mortality", "APR死亡风险", "临床分组", "apr_risk_of_mortality IN (N'Minor',N'Moderate',N'Major',N'Extreme')"),
    FieldSpec("apr_medical_surgical_desc", "医疗/手术类型", "临床分组", "apr_medical_surgical_desc IN (N'Medical',N'Surgical')"),
    FieldSpec("payment_typology_1", "主要支付方式", "支付信息"),
    FieldSpec("payment_typology_2", "第二支付方式", "支付信息", conditional=True),
    FieldSpec("payment_typology_3", "第三支付方式", "支付信息", conditional=True),
    FieldSpec("birth_weight", "出生体重", "新生儿信息", "TRY_CONVERT(INT,birth_weight) BETWEEN 1 AND 10000", "type_of_admission=N'Newborn'"),
    FieldSpec("emergency_department_indicator", "急诊标志", "就诊过程", "emergency_department_indicator IN (N'Y',N'N')"),
    FieldSpec("total_charges", "总账单费用", "费用信息", "TRY_CONVERT(FLOAT,total_charges)>=0"),
    FieldSpec("total_costs", "总实际成本", "费用信息", "TRY_CONVERT(FLOAT,total_costs)>=0"),
)


def _pct(numerator, denominator):
    denominator = int(denominator or 0)
    return round(float(numerator or 0) * 100 / denominator, 2) if denominator else None


def field_quality_matrix() -> dict:
    select = ["discharge_year AS [year]", "COUNT_BIG(*) AS records"]
    for index, spec in enumerate(FIELDS):
        present = _present(spec.field)
        applicable = spec.applicable or "1=1"
        valid = spec.valid or present
        select.extend([
            f"SUM(CASE WHEN {applicable} THEN 1 ELSE 0 END) AS f{index}_applicable",
            f"SUM(CASE WHEN ({applicable}) AND ({present}) THEN 1 ELSE 0 END) AS f{index}_present",
            f"SUM(CASE WHEN ({applicable}) AND ({present}) AND ({valid}) THEN 1 ELSE 0 END) AS f{index}_valid",
        ])
    rows = aggregation._run_query(
        f"SELECT {','.join(select)} FROM {storage.TABLE_NAME} GROUP BY discharge_year ORDER BY discharge_year"
    )
    fields = []
    for index, spec in enumerate(FIELDS):
        yearly = []
        total_records = total_applicable = total_present = total_valid = 0
        for row in rows:
            records = int(row.get("records") or 0)
            applicable = int(row.get(f"f{index}_applicable") or 0)
            present = int(row.get(f"f{index}_present") or 0)
            valid = int(row.get(f"f{index}_valid") or 0)
            total_records += records
            total_applicable += applicable
            total_present += present
            total_valid += valid
            completeness = None if spec.conditional else _pct(present, applicable)
            validity = _pct(valid, present)
            score = None if spec.conditional else round((completeness + validity) / 2, 2) if completeness is not None and validity is not None else None
            yearly.append({
                "year": int(row["year"]), "records": records,
                "applicable_records": None if spec.conditional else applicable,
                "present_records": present, "coverage_pct": _pct(present, records),
                "completeness_pct": completeness, "validity_pct": validity, "score_pct": score,
            })
        overall_completeness = None if spec.conditional else _pct(total_present, total_applicable)
        overall_validity = _pct(total_valid, total_present)
        overall_score = None if spec.conditional else round((overall_completeness + overall_validity) / 2, 2) if overall_completeness is not None and overall_validity is not None else None
        value_key = "coverage_pct" if spec.conditional else "score_pct"
        values = [item[value_key] for item in yearly if item[value_key] is not None]
        fields.append({
            "field": spec.field, "label": spec.label, "domain": spec.domain,
            "conditional": spec.conditional, "metric_label": "覆盖率" if spec.conditional else "质量分",
            "records": total_records, "applicable_records": None if spec.conditional else total_applicable,
            "present_records": total_present, "coverage_pct": _pct(total_present, total_records),
            "completeness_pct": overall_completeness, "validity_pct": overall_validity,
            "score_pct": overall_score,
            "change_pct": round(values[-1] - values[0], 2) if len(values) > 1 else None,
            "yearly": yearly,
        })
    return {
        "years": [int(row["year"]) for row in rows], "field_count": len(fields), "fields": fields,
        "caveat": "手术/操作及第二、第三支付方式属于条件字段，展示总体覆盖率，不将合理空值计为质量缺失；出生体重仅在新生儿入院记录中评估。",
    }
