import time

from flask import Blueprint

from ..services.disease_service import DiseaseService
from .common import analytics_response, repository
from .params import parse_query_params


blueprint = Blueprint("disease", __name__)


@blueprint.get("/api/diseases/top")
def diseases_top():
    started = time.perf_counter()
    filters, limit = parse_query_params()
    data = DiseaseService(repository()).top(filters, limit)
    return analytics_response(data, started, "disease", "record_count", filters)

