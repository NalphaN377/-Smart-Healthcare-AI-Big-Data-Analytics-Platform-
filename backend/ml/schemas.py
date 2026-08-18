from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


AgeGroup = Literal["0 to 17", "18 to 29", "30 to 49", "50 to 69", "70 or Older"]
Gender = Literal["F", "M", "U"]
AdmissionType = Literal["Elective", "Emergency", "Newborn", "Trauma", "Urgent"]
Severity = Literal["Minor", "Moderate", "Major", "Extreme"]
MortalityRisk = Literal["Minor", "Moderate", "Major", "Extreme"]
MedicalSurgical = Literal["Medical", "Surgical", "Not Applicable"]
PaymentType = Literal[
    "Blue Cross/Blue Shield",
    "Department of Corrections",
    "Federal/State/Local/VA",
    "Managed Care, Unspecified",
    "Medicaid",
    "Medicare",
    "Miscellaneous/Other",
    "Private Health Insurance",
    "Self-Pay",
]


class CostPredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    age_group: AgeGroup
    gender: Gender
    admission_type: AdmissionType
    diagnosis_code: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9.]+$")
    severity: Severity
    mortality_risk: MortalityRisk
    medical_surgical_description: MedicalSurgical
    emergency_indicator: bool
    payment_type_1: PaymentType

    @field_validator("diagnosis_code")
    @classmethod
    def normalize_diagnosis_code(cls, value: str) -> str:
        return value.upper()
