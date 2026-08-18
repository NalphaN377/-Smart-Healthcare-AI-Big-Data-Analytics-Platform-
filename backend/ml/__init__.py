"""Inpatient cost estimation module for analysis and teaching use."""

from .schemas import CostPredictionRequest
from .service import CostPredictionService, ModelUnavailableError

__all__ = ["CostPredictionRequest", "CostPredictionService", "ModelUnavailableError"]
