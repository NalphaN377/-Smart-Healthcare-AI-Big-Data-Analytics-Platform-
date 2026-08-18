import time

from flask import Blueprint

from .common import analytics_response, repository
from .params import parse_query_params


blueprint = Blueprint("payment", __name__)


@blueprint.get("/api/payments/distribution")
def payment_distribution():
    started = time.perf_counter()
    filters, limit = parse_query_params()
    data = repository().payment_distribution(filters, limit)
    return analytics_response(data, started, "payment_type_1", "record_count", filters)
