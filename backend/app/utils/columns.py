from __future__ import annotations

import re
import unicodedata


# Source fields are normalized into this stable internal contract. Derived fields
# (length_of_stay_raw, source metadata and record_hash) are added by cleaning.
SOURCE_COLUMNS = [
    "hospital_service_area",
    "hospital_county",
    "operating_certificate_number",
    "facility_id",
    "facility_name",
    "age_group",
    "zip_code_3_digits",
    "gender",
    "race",
    "ethnicity",
    "length_of_stay",
    "admission_type",
    "patient_disposition",
    "discharge_year",
    "diagnosis_code",
    "diagnosis_description",
    "procedure_code",
    "procedure_description",
    "apr_drg_code",
    "apr_drg_description",
    "apr_mdc_code",
    "apr_mdc_description",
    "severity_code",
    "severity",
    "mortality_risk",
    "medical_surgical_description",
    "payment_type_1",
    "payment_type_2",
    "payment_type_3",
    "birth_weight",
    "emergency_indicator",
    "total_charges",
    "total_costs",
]

BUSINESS_COLUMNS = [
    *SOURCE_COLUMNS[:10],
    "length_of_stay_raw",
    *SOURCE_COLUMNS[10:],
]

OUTPUT_COLUMNS = [
    *BUSINESS_COLUMNS,
    "source_file",
    "source_row_number",
    "record_hash",
]

IMPORTANT_COLUMNS = {
    "age_group",
    "gender",
    "length_of_stay",
    "discharge_year",
    "diagnosis_description",
    "severity",
    "payment_type_1",
    "birth_weight",
    "emergency_indicator",
    "total_charges",
    "total_costs",
}


def normalize_header(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value)).lstrip("\ufeff").strip().casefold()
    text = text.replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


_ALIASES = {
    "hospital_service_area": ["Hospital Service Area"],
    "hospital_county": ["Hospital County"],
    "operating_certificate_number": ["Operating Certificate Number", "Operating Certificate Num"],
    "facility_id": ["Permanent Facility Id", "Permanent Facility ID", "Facility ID"],
    "facility_name": ["Facility Name", "Hospital Name"],
    "age_group": ["Age Group", "Age Group Category"],
    "zip_code_3_digits": ["Zip Code - 3 digits", "Zip Code 3 digits", "Zip Code - 3 Digits"],
    "gender": ["Gender", "Sex"],
    "race": ["Race"],
    "ethnicity": ["Ethnicity"],
    "length_of_stay": ["Length of Stay", "Length Of Stay"],
    "admission_type": ["Type of Admission", "Admission Type"],
    "patient_disposition": ["Patient Disposition", "Discharge Disposition"],
    "discharge_year": ["Discharge Year", "Year"],
    "diagnosis_code": ["CCSR Diagnosis Code", "CCS Diagnosis Code", "Diagnosis Code"],
    "diagnosis_description": [
        "CCSR Diagnosis Description",
        "CCS Diagnosis Description",
        "Diagnosis Description",
    ],
    "procedure_code": ["CCSR Procedure Code", "CCS Procedure Code", "Procedure Code"],
    "procedure_description": [
        "CCSR Procedure Description",
        "CCS Procedure Description",
        "Procedure Description",
    ],
    "apr_drg_code": ["APR DRG Code"],
    "apr_drg_description": ["APR DRG Description"],
    "apr_mdc_code": ["APR MDC Code"],
    "apr_mdc_description": ["APR MDC Description"],
    "severity_code": ["APR Severity of Illness Code", "Severity of Illness Code"],
    "severity": ["APR Severity of Illness Description", "Severity of Illness Description"],
    "mortality_risk": ["APR Risk of Mortality", "Risk of Mortality"],
    "medical_surgical_description": [
        "APR Medical Surgical Description",
        "APR Medical/Surgical Description",
        "Medical Surgical Description",
    ],
    "payment_type_1": ["Payment Typology 1", "Payment Type 1"],
    "payment_type_2": ["Payment Typology 2", "Payment Type 2"],
    "payment_type_3": ["Payment Typology 3", "Payment Type 3"],
    "birth_weight": ["Birth Weight", "Birthweight"],
    "emergency_indicator": [
        "Emergency Department Indicator",
        "Emergency Dept Indicator",
        "ED Indicator",
    ],
    "total_charges": ["Total Charges", "Total Charge"],
    "total_costs": ["Total Costs", "Total Cost"],
}


COLUMN_MAPPING = {
    normalize_header(alias): canonical
    for canonical, aliases in _ALIASES.items()
    for alias in [canonical, *aliases]
}


def resolve_columns(raw_columns: list[str]) -> tuple[dict[str, str], list[str]]:
    mapping: dict[str, str] = {}
    detected: set[str] = set()
    for raw in raw_columns:
        canonical = COLUMN_MAPPING.get(normalize_header(raw))
        if canonical:
            mapping[raw] = canonical
            detected.add(canonical)
    missing = [column for column in SOURCE_COLUMNS if column not in detected]
    return mapping, missing
