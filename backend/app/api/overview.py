import time

from flask import Blueprint

from ..services.overview_service import OverviewService
from .common import analytics_response, repository
from .params import parse_query_params


blueprint = Blueprint("overview", __name__)


@blueprint.get("/api/overview")
def overview():
    started = time.perf_counter()
    filters, _ = parse_query_params(include_limit=False)
    data = OverviewService(repository()).get(filters)
    return analytics_response(data, started, "overview", "summary", filters)

