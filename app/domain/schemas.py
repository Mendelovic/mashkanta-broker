"""Domain schemas for structured intake and mortgage planning."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, PositiveFloat


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
    employment_status: Optional[str] = Field(
        default=None, description="e.g., salaried, self-employed, public sector"
    )
    age_years: Optional[AgeRange] = None
    dependents: Optional[SmallIntRange] = None
    income_volatility_factor: Optional[VolatilityFactor] = Field(
        default=None,
        description="0=stable, 1=highly volatile. Used to buffer payment stress.",
    )
    notes: Optional[str] = None


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
    cpi_tolerance: SliderInt
    prime_exposure_preference: SliderInt
    max_payment_nis: Optional[PositiveFloat] = None
    red_line_payment_nis: Optional[PositiveFloat] = None
    expected_prepay_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    expected_prepay_month: Optional[PrepayMonth] = None
    rate_view: RateView = RateView.FLAT
    additional_signals: List[PreferenceSignal] = Field(default_factory=list)


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
    loan: LoanAsk
    preferences: Preferences
    future_plans: List[FuturePlan] = Field(default_factory=list)
    quotes: Optional[Quotes] = None
    interview_summary: Optional[str] = Field(
        default=None, description="Teach-back paragraph confirmed with the borrower."
    )


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
    cpi_share_max: float
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


class UniformBasket(BaseModel):
    """Representation of a BOI uniform basket benchmark."""

    name: str
    shares: TrackShares


class TrackDetail(BaseModel):
    """Describes a single track component within a mix."""

    track: str
    amount_nis: float
    rate_display: str
    indexation: str
    reset_note: str


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
    five_year_cost_nis: float
    total_weighted_cost_nis: float
    variable_share_pct: float
    cpi_share_pct: float
    ltv_ratio: float
    prepayment_fee_exposure: str
    track_details: List["TrackDetail"]


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
    assumptions: Dict[str, Any] = Field(default_factory=dict)
