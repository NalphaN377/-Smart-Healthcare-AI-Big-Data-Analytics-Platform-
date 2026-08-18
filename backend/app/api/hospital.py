import time

from flask import Blueprint

from ..services.hospital_service import HospitalService
from .common import analytics_response, repository
from .params import parse_query_params


blueprint = Blueprint("hospital", __name__)


@blueprint.get("/api/hospitals/top")
def hospitals_top():
    started = time.perf_counter()
    filters, limit = parse_query_params()
    data = HospitalService(repository()).top(filters, limit)
    return analytics_response(data, started, "hospital", "record_count", filters)

