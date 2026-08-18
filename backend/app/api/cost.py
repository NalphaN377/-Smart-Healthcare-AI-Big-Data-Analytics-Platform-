import time

from flask import Blueprint

from ..services.cost_service import CostService
from .common import analytics_response, repository
from .params import parse_query_params


blueprint = Blueprint("cost", __name__)


@blueprint.get("/api/diseases/cost")
def diseases_cost():
    started = time.perf_counter()
    filters, limit = parse_query_params()
    data = CostService(repository()).diseases(filters, limit)
    return analytics_response(data, started, "disease", "average_cost", filters)


@blueprint.get("/api/hospitals/cost")
def hospitals_cost():
    started = time.perf_counter()
    filters, limit = parse_query_params()
    data = CostService(repository()).hospitals(filters, limit)
    return analytics_response(data, started, "hospital", "average_cost", filters)

