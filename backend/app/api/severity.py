import time

from flask import Blueprint

from .common import analytics_response, repository
from .params import parse_query_params


blueprint = Blueprint("severity", __name__)


@blueprint.get("/api/severity/distribution")
def severity_distribution():
    started = time.perf_counter()
    filters, limit = parse_query_params()
    data = repository().severity_distribution(filters, limit)
    return analytics_response(data, started, "severity", "record_count", filters)

