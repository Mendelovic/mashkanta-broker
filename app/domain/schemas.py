"""Domain schemas for structured intake and mortgage planning."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import (
    BaseModel,
    Field,
    PositiveFloat,
    ValidationInfo,
    field_validator,
    model_validator,
)


AgeRange = Annotated[int, Field(ge=18, le=85)]
SmallIntRange = Annotated[int, Field(ge=0, le=10)]
SliderInt = Annotated[int, Field(ge=0, le=10)]
LoanTerm = Annotated[int, Field(ge=1, le=30)]
StartMonth = Annotated[int, Field(ge=1, le=12)]
PrepayMonth = Annotated[int, Field(ge=1, le=360)]
FutureTimeframe = Annotated[int, Field(ge=0, le=240)]
PreferenceScore = Annotated[float, Field(ge=0.0, le=10.0)]
PreferenceWeight = Annotated[float, Field(ge=0.0, le=1.0)]
VolatilityFactor = Annotated[float, Field(ge=0.0, le=1.0)]


def _parse_currency_amount(value: Any) -> Optional[float]:
    """Parse various user-entered currency representations into a float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        cleaned = cleaned.replace("₪", "").replace(",", "").replace(" ", "")
        multiplier = 1.0
        if cleaned and cleaned[-1] in {"k", "K"}:
            multiplier = 1_000.0
            cleaned = cleaned[:-1]
        elif cleaned and cleaned[-1] in {"m", "M"}:
            multiplier = 1_000_000.0
            cleaned = cleaned[:-1]
        try:
            return float(cleaned) * multiplier
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid currency amount: {value}") from exc
    raise TypeError(f"Unsupported currency type: {type(value)!r}")  # pragma: no cover


def _parse_range_bounds(raw: str) -> Optional[tuple[float, float]]:
    separators = ("-", "–", "—", "עד", "to", "עד")
    if not any(sep in raw for sep in separators):
        return None

    import re

    parts = [
        part.strip()
        for part in re.split(r"\s*(?:-|–|—|עד|עד|to)\s*", raw, maxsplit=2)
        if part.strip()
    ]
    if len(parts) >= 2:
        try:
            lower = _parse_currency_amount(parts[0])
            upper = _parse_currency_amount(parts[1])
        except (TypeError, ValueError):
            return None
        if lower is None or upper is None:
            return None
        lower, upper = sorted((lower, upper))
        return lower, upper
    if len(parts) == 1 and "עד" in raw:
        upper = _parse_currency_amount(parts[0])
        if upper is None:
            return None
        return upper * 0.9, upper
    return None


class ResidencyStatus(str, Enum):
    """Residency status relevant for regulatory exceptions."""

    RESIDENT = "resident"
    NON_RESIDENT = "non_resident"


class OccupancyIntent(str, Enum):
    """Whether the borrower will occupy the property."""

    OWN = "own"
    RENT = "rent"


class DealType(str, Enum):
    """Primary Bank-of-Israel deal categories."""

    FIRST_HOME = "first_home"
    REPLACEMENT = "replacement"
    INVESTMENT = "investment"


class PropertyType(str, Enum):
    """Property usage classification."""

    SINGLE = "single"
    REPLACEMENT = "replacement"
    INVESTMENT = "investment"


DEAL_TO_PROPERTY_MAP: Dict["DealType", PropertyType] = {
    DealType.FIRST_HOME: PropertyType.SINGLE,
    DealType.REPLACEMENT: PropertyType.REPLACEMENT,
    DealType.INVESTMENT: PropertyType.INVESTMENT,
}


class RateAnchor(str, Enum):
    """Reference anchors used for quoted tracks."""

    PRIME = "prime"
    GOV_5Y = "gov5y"
    GOV_10Y = "gov10y"
    OTHER = "other"


class RateView(str, Enum):
    """Borrower view on rate trajectory."""

    FALL = "fall"
    FLAT = "flat"
    RISE = "rise"


class BorrowerProfile(BaseModel):
    """Validated borrower-level inputs."""

    primary_applicant_name: Optional[str] = None
    co_applicant_names: List[str] = Field(default_factory=list)
    residency: ResidencyStatus = ResidencyStatus.RESIDENT
    occupancy: OccupancyIntent = OccupancyIntent.OWN
    net_income_nis: PositiveFloat = Field(
        ..., description="Disposable monthly income in NIS"
    )
    fixed_expenses_nis: float = Field(
        default=0.0,
        ge=0.0,
        description="Monthly fixed obligations counted in PTI (loans >18m, alimony, rent if not occupying).",
    )
    additional_income_nis: float = Field(default=0.0, ge=0.0)
    employment_status: str = Field(
        ..., description="e.g., salaried, self-employed, public sector"
    )
    employment_tenure_months: Optional[int] = Field(
        default=None,
        ge=0,
        le=600,
        description="Approximate number of months in current role.",
    )
    has_recent_credit_issues: bool = Field(
        ...,
        description="True if the borrower reports recent credit flags (returned debit, collections, etc.).",
    )
    age_years: Optional[AgeRange] = None
    dependents: Optional[SmallIntRange] = None
    income_volatility_factor: Optional[VolatilityFactor] = Field(
        default=None,
        description="0=stable, 1=highly volatile. Used to buffer payment stress.",
    )
    notes: Optional[str] = None
    equity_provenance: Optional[str] = Field(
        default=None,
        description="Source of equity (savings, gifts, sale, etc.) and transfer status.",
    )
    gift_letter_required: Optional[bool] = Field(
        default=None, description="True if a gift letter will be needed."
    )
    employer_stability_notes: Optional[str] = Field(
        default=None,
        description="Employer type, sector stability, probation status, and tenure context.",
    )

    @model_validator(mode="after")
    def _validate_employment_fields(self) -> "BorrowerProfile":
        if self.employment_tenure_months is None:
            raise ValueError(
                "employment_tenure_months must be provided for borrower profile."
            )
        return self


class PropertyDetails(BaseModel):
    """Details about the property being financed."""

    type: PropertyType
    value_nis: PositiveFloat
    address_city: Optional[str] = None
    address_region: Optional[str] = None
    is_new_build: bool = False
    target_close_months: Optional[FutureTimeframe] = Field(
        default=None, description="Months until expected closing/draw."
    )
    builder_name: Optional[str] = None
    appraisal_value_nis: Optional[PositiveFloat] = None
    title_notes: Optional[str] = Field(
        default=None,
        description="Notes on rights/registration (Tabu, Minhal, Hevra Meshakenet, TAMA status, easements).",
    )


class LoanAsk(BaseModel):
    """Loan request parameters."""

    amount_nis: PositiveFloat
    term_years: LoanTerm
    currency: Literal["NIS", "FX"] = "NIS"
    target_draw_date: Optional[date] = None
    desired_start_month: Optional[StartMonth] = None


class PreferenceSignal(BaseModel):
    """Generic representation of a fuzzy preference."""

    name: str
    score: Optional[PreferenceScore] = None
    weight: Optional[PreferenceWeight] = None
    unit: Optional[str] = None
    rationale: Optional[str] = None


class Preferences(BaseModel):
    """Collects structured and fuzzy preferences."""

    stability_vs_cost: SliderInt
    cpi_tolerance: Optional[SliderInt] = None
    prime_exposure_preference: Optional[SliderInt] = None
    max_payment_nis: Optional[PositiveFloat] = None
    red_line_payment_nis: Optional[PositiveFloat] = None
    expected_prepay_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    expected_prepay_month: Optional[PrepayMonth] = None
    prepayment_confirmed: bool = False
    rate_view: RateView = RateView.FLAT
    additional_signals: List[PreferenceSignal] = Field(default_factory=list)

    _MIN_PAYMENT_AMOUNT_NIS = 100.0

    @field_validator("max_payment_nis", "red_line_payment_nis", mode="before")
    @classmethod
    def _coerce_payment_amount(
        cls, value: Any, info: ValidationInfo
    ) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, str):
            bounds = _parse_range_bounds(value)
            if bounds is not None:
                lower, upper = bounds
                if info.field_name == "max_payment_nis":
                    return (lower + upper) / 2.0
                return upper

        parsed = _parse_currency_amount(value)
        return parsed

    @model_validator(mode="after")
    def _validate_payment_targets(self) -> "Preferences":
        if (
            self.red_line_payment_nis is not None
            and self.max_payment_nis is not None
            and self.red_line_payment_nis < self.max_payment_nis
        ):
            raise ValueError(
                "red_line_payment_nis must be greater than or equal to max_payment_nis"
            )
        if (
            self.max_payment_nis is not None
            and self.max_payment_nis < self._MIN_PAYMENT_AMOUNT_NIS
        ):
            raise ValueError(
                f"max_payment_nis must be at least {self._MIN_PAYMENT_AMOUNT_NIS:.0f} NIS."
            )
        if (
            self.red_line_payment_nis is not None
            and self.red_line_payment_nis < self._MIN_PAYMENT_AMOUNT_NIS
        ):
            raise ValueError(
                f"red_line_payment_nis must be at least {self._MIN_PAYMENT_AMOUNT_NIS:.0f} NIS."
            )
        return self


class FuturePlan(BaseModel):
    """Forward-looking events the borrower anticipates."""

    category: Literal[
        "family",
        "career",
        "education",
        "income_change",
        "relocation",
        "other",
    ]
    timeframe_months: Optional[FutureTimeframe] = None
    expected_income_delta_nis: Optional[float] = None
    confidence: Optional[PreferenceWeight] = None
    notes: Optional[str] = None


class QuoteTrack(BaseModel):
    """Represents a quoted track from a bank."""

    track: Literal[
        "fixed_unindexed",
        "fixed_cpi",
        "variable_prime",
        "variable_cpi",
        "variable_unindexed",
    ]
    rate_anchor: RateAnchor
    margin_pct: float = Field(
        ..., description="Spread versus anchor, e.g. prime-0.4 => -0.4"
    )
    bank_name: Optional[str] = None


class Quotes(BaseModel):
    """Container for multiple quoted tracks."""

    tracks: List[QuoteTrack] = Field(default_factory=list)

    def to_track_map(self) -> Dict[str, QuoteTrack]:
        return {track.track: track for track in self.tracks}


class InterviewRecord(BaseModel):
    """Structured output of the intake conversation."""

    borrower: BorrowerProfile
    property: PropertyDetails
    deal_type: DealType = DealType.FIRST_HOME
    loan: LoanAsk
    preferences: Preferences
    future_plans: List[FuturePlan] = Field(default_factory=list)
    quotes: Optional[Quotes] = None
    interview_summary: Optional[str] = Field(
        default=None, description="Teach-back paragraph confirmed with the borrower."
    )

    @model_validator(mode="after")
    def _align_deal_type(self) -> "InterviewRecord":
        fields_set = getattr(self, "model_fields_set", set())
        occupancy = self.borrower.occupancy
        current_usage = self.property.type

        def infer_deal() -> DealType:
            if current_usage == PropertyType.REPLACEMENT:
                return DealType.REPLACEMENT
            if occupancy == OccupancyIntent.RENT:
                return DealType.INVESTMENT
            if (
                current_usage == PropertyType.INVESTMENT
                and occupancy == OccupancyIntent.OWN
            ):
                return DealType.FIRST_HOME
            if current_usage == PropertyType.INVESTMENT:
                return DealType.INVESTMENT
            return DealType.FIRST_HOME

        if "deal_type" not in fields_set:
            self.deal_type = infer_deal()

        if occupancy == OccupancyIntent.OWN and self.deal_type == DealType.INVESTMENT:
            raise ValueError("Owner-occupied deals cannot be classified as investment.")
        if occupancy == OccupancyIntent.RENT and self.deal_type == DealType.FIRST_HOME:
            raise ValueError("Deals marked as first_home must be owner-occupied.")

        enforced_usage = DEAL_TO_PROPERTY_MAP.get(self.deal_type, PropertyType.SINGLE)
        if self.property.type != enforced_usage:
            self.property = self.property.model_copy(update={"type": enforced_usage})

        return self


class IntakeSubmission(BaseModel):
    """Payload submitted by the agent when intake concludes."""

    record: InterviewRecord
    confirmation_notes: Optional[List[str]] = None


class PreferenceWeights(BaseModel):
    """Calculated weights applied during optimization."""

    expected_cost: float = 1.0
    payment_volatility: float
    cpi_exposure: float
    prepay_fee_exposure: float


class SoftCaps(BaseModel):
    """Soft caps derived from preferences."""

    variable_share_max: float
    cpi_share_max: Optional[float] = None
    payment_ceiling_nis: Optional[float] = None


class ScenarioWeights(BaseModel):
    """Scenario weights for rate outlook."""

    fall: float
    flat: float
    rise: float


class PrepaymentEvent(BaseModel):
    """Represents an anticipated prepayment event."""

    month: int
    pct_of_balance: float
    notes: Optional[str] = None


class PlanningContext(BaseModel):
    """Derived planning inputs consumed by optimization/eligibility tools."""

    weights: PreferenceWeights
    soft_caps: SoftCaps
    scenario_weights: ScenarioWeights
    prepayment_schedule: List[PrepaymentEvent] = Field(default_factory=list)
    income_timeline: List[float] = Field(default_factory=list)
    expense_timeline: List[float] = Field(default_factory=list)
    pti_targets: List[float] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FeasibilityIssue(BaseModel):
    """Represents a blocking issue discovered during quick feasibility checks."""

    code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class FeasibilityResult(BaseModel):
    """Summary of the quick feasibility check run during intake triage."""

    is_feasible: bool
    ltv_ratio: float
    ltv_limit: float
    pti_ratio: float
    pti_limit: float
    pti_ratio_peak: Optional[float] = None
    variable_share_pct: Optional[float] = None
    variable_share_limit_pct: Optional[float] = None
    loan_term_years: Optional[int] = None
    loan_term_limit_years: Optional[int] = None
    issues: List[FeasibilityIssue] = Field(default_factory=list)


class TrackShares(BaseModel):
    """Distribution of loan across track categories."""

    fixed_unindexed: float
    fixed_cpi: float
    variable_prime: float
    variable_cpi: float

    def total(self) -> float:
        return (
            self.fixed_unindexed
            + self.fixed_cpi
            + self.variable_prime
            + self.variable_cpi
        )


class TrackDetail(BaseModel):
    """Describes a single track component within a mix."""

    track: str
    amount_nis: float
    rate_display: str
    indexation: str
    reset_note: str
    anchor_rate_pct: Optional[float] = None


class PaymentSensitivity(BaseModel):
    """Represents payment under a simple shock scenario."""

    scenario: str
    payment_nis: float


class MixMetrics(BaseModel):
    """Metrics describing payments and risk for a candidate mix."""

    monthly_payment_nis: float
    pti_ratio: float
    pti_ratio_peak: float
    total_interest_paid: float
    max_payment_under_stress: float
    average_rate_pct: float
    expected_weighted_payment_nis: float
    highest_expected_payment_nis: float
    highest_expected_payment_note: Optional[str] = Field(
        default=None,
        description="Explanation of the highest expected payment disclosure.",
    )
    peak_payment_month: Optional[int] = None
    peak_payment_driver: Optional[str] = None
    five_year_total_payment_nis: float
    total_weighted_cost_nis: float
    variable_share_pct: float
    cpi_share_pct: float
    ltv_ratio: float
    prepayment_fee_exposure: str
    track_details: List["TrackDetail"]
    payment_sensitivity: List["PaymentSensitivity"]


class TermSweepEntry(BaseModel):
    """Summary metrics for a specific term length."""

    term_years: int
    monthly_payment_nis: float
    stress_payment_nis: float
    expected_weighted_payment_nis: float
    pti_ratio: float
    pti_ratio_peak: float


class OptimizationCandidate(BaseModel):
    """A single mix candidate produced by the optimizer."""

    label: str
    shares: TrackShares
    metrics: MixMetrics
    feasibility: FeasibilityResult | None = None
    notes: List[str] = Field(default_factory=list)


class OptimizationResult(BaseModel):
    """Final optimizer output containing benchmarks and best-effort mix."""

    candidates: List[OptimizationCandidate]
    recommended_index: int
    engine_recommended_index: Optional[int] = None
    advisor_recommended_index: Optional[int] = None
    term_sweep: List[TermSweepEntry] = Field(default_factory=list)
    assumptions: Dict[str, Any] = Field(default_factory=dict)
