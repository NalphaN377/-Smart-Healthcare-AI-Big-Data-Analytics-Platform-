from __future__ import annotations

from datetime import datetime

from flask import current_app, request


class ValidationError(ValueError):
    pass


def parse_query_params(include_limit: bool = True) -> tuple[dict, int]:
    allowed = {"year", "age_group", "hospital", "diagnosis"}
    if include_limit:
        allowed.add("limit")
    unknown = sorted(set(request.args.keys()) - allowed)
    if unknown:
        raise ValidationError("Unsupported query parameter(s): " + ", ".join(unknown))

    limit = 10
    if include_limit and "limit" in request.args:
        try:
            limit = int(request.args["limit"])
        except (TypeError, ValueError) as exc:
            raise ValidationError("limit must be an integer") from exc
        maximum = int(current_app.config.get("MAX_QUERY_LIMIT", 100))
        if not 1 <= limit <= maximum:
            raise ValidationError(f"limit must be between 1 and {maximum}")

    filters: dict[str, object] = {}
    if "year" in request.args:
        try:
            year = int(request.args["year"])
        except (TypeError, ValueError) as exc:
            raise ValidationError("year must be an integer") from exc
        if not 1900 <= year <= datetime.now().year + 1:
            raise ValidationError("year is outside the supported range")
        filters["year"] = year

    for key in ("age_group", "hospital", "diagnosis"):
        if key not in request.args:
            continue
        value = request.args[key].strip()
        if not value:
            raise ValidationError(f"{key} cannot be empty")
        if len(value) > 255 or any(ord(character) < 32 for character in value):
            raise ValidationError(f"{key} is too long or contains control characters")
        filters[key] = value
    return filters, limit

