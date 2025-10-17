"""Centralized Bank of Israel mortgage constraints used across the service layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping

from app.domain.schemas import DealType, OccupancyIntent, PropertyType

# ---------------------------------------------------------------------------
# Core quantitative guardrails (Directive 329)
# ---------------------------------------------------------------------------

# Payment-to-income regulatory cap (DSTI) and warning threshold for elevated risk.
PTI_REGULATORY_LIMIT: float = 0.50
PTI_WARNING_THRESHOLD: float = 0.40

# Loan-to-value ceilings by property classification / deal type.
LTV_LIMITS_BY_PROPERTY: Mapping[PropertyType, float] = {
    PropertyType.SINGLE: 0.75,
    PropertyType.REPLACEMENT: 0.70,
    PropertyType.INVESTMENT: 0.50,
}

LTV_LIMITS_BY_DEAL: Mapping[DealType, float] = {
    DealType.FIRST_HOME: LTV_LIMITS_BY_PROPERTY[PropertyType.SINGLE],
    DealType.REPLACEMENT: LTV_LIMITS_BY_PROPERTY[PropertyType.REPLACEMENT],
    DealType.INVESTMENT: LTV_LIMITS_BY_PROPERTY[PropertyType.INVESTMENT],
}

# Variable-rate exposure share (prime + 5y reset tracks).
VARIABLE_SHARE_LIMIT: float = 2 / 3

# Maximum permitted term in years.
MAX_TERM_YEARS: int = 30

# Buyer-price valuation cap for LTV computation (§329 4a).
BUYER_PRICE_APPRAISAL_CAP_NIS: float = 1_800_000.0


@dataclass(frozen=True)
class VariableShareExceptionRules:
    """Directive 329 §12 exception thresholds that relax the variable-share cap."""

    max_bridge_term_months: int = 36
    any_purpose_amount_nis: float = 120_000.0


VARIABLE_SHARE_EXCEPTIONS = VariableShareExceptionRules()


# PTI computation notes (appendix 329 1.2-1.3).
PTI_OCCUPANCY_RENT_DEDUCTION: Dict[OccupancyIntent, bool] = {
    OccupancyIntent.OWN: False,
    OccupancyIntent.RENT: True,
}
