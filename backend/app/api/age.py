import time

from flask import Blueprint

from .common import analytics_response, repository
from .params import parse_query_params


blueprint = Blueprint("age", __name__)


@blueprint.get("/api/age/distribution")
def age_distribution():
    started = time.perf_counter()
    filters, limit = parse_query_params()
    data = repository().age_distribution(filters, limit)
    return analytics_response(data, started, "age_group", "record_count", filters)


@blueprint.get("/api/age/cost")
def age_cost():
    started = time.perf_counter()
    filters, limit = parse_query_params()
    data = repository().age_cost(filters, limit)
    return analytics_response(data, started, "age_group", "average_cost", filters)

