"""Role and permission definitions shared by authentication services."""

ROLE_PERMISSIONS = {
    "patient": {
        "overview:read",
        "ai:basic",
        "cost_prediction:use",
        "report:public:read",
    },
    "doctor": {
        "overview:read",
        "ai:advanced",
        "cost_prediction:use",
        "report:public:read",
        "data_asset:read",
        "patient_profile:read",
        "report:generate",
        "data:export",
    },
    "admin": {
        "overview:read",
        "ai:advanced",
        "cost_prediction:use",
        "report:public:read",
        "data_asset:read",
        "patient_profile:read",
        "report:generate",
        "data:export",
        "ingestion:manage",
        "user:manage",
        "system:manage",
        "audit:read",
    },
}

ROLE_LABELS = {"patient": "患者用户", "doctor": "医生用户", "admin": "运维员用户"}


def permissions_for(role: str) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, set()))


def has_permission(user: dict | None, permission: str) -> bool:
    return bool(user and permission in ROLE_PERMISSIONS.get(user.get("role"), set()))
