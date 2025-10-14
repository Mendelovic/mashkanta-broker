"""Mix optimization utilities for mortgage compositions."""

from __future__ import annotations

from typing import Dict, List

from app.configuration.menu_loader import load_average_menu_rates
from app.domain.schemas import (
    InterviewRecord,
    MixMetrics,
    OptimizationCandidate,
    OptimizationResult,
    PlanningContext,
    RateAnchor,
    TrackShares,
    TrackDetail,
    UniformBasket,
)
from app.services.deal_feasibility import run_feasibility_checks

BASE_ANCHOR_RATES: Dict[RateAnchor, float] = {
    RateAnchor.PRIME: 0.06,
    RateAnchor.GOV_5Y: 0.032,
    RateAnchor.GOV_10Y: 0.035,
    RateAnchor.OTHER: 0.04,
}

DEFAULT_TRACK_RATES: Dict[str, float] = {
    "fixed_unindexed": 0.049,
    "fixed_cpi": 0.0302,
    "variable_prime": 0.0515,
    "variable_unindexed": 0.0482,
    "variable_cpi": 0.0305,
}

_MENU_TRACK_RATES = load_average_menu_rates()


def _estimate_prepayment_exposure(shares: TrackShares) -> str:
    fixed_share = shares.fixed_unindexed + shares.fixed_cpi
    if fixed_share >= 0.6:
        return "high"
    if fixed_share >= 0.3:
        return "medium"
    return "low"


def _format_margin(prefix: str, margin: float) -> str:
    margin_pct = margin * 100
    sign = "+" if margin_pct >= 0 else ""
    return f"{prefix}{sign}{margin_pct:.2f}%"


def _build_track_details(
    shares: TrackShares, loan_amount: float, rate_table: Dict[str, float]
) -> List[TrackDetail]:
    details: List[TrackDetail] = []

    def add_detail(
        track: str, share: float, rate_display: str, indexation: str, reset_note: str
    ) -> None:
        if share <= 0:
            return
        amount = loan_amount * share
        details.append(
            TrackDetail(
                track=track,
                amount_nis=amount,
                rate_display=rate_display,
                indexation=indexation,
                reset_note=reset_note,
            )
        )

    prime_rate = rate_table.get("variable_prime")
    if prime_rate is not None:
        margin = prime_rate - BASE_ANCHOR_RATES[RateAnchor.PRIME]
        add_detail(
            "variable_prime",
            shares.variable_prime,
            _format_margin("P", margin),
            "none",
            "Prime-linked (monthly updates)",
        )

    fixed_unlinked_rate = rate_table.get("fixed_unindexed")
    if fixed_unlinked_rate is not None:
        add_detail(
            "fixed_unindexed",
            shares.fixed_unindexed,
            f"{fixed_unlinked_rate * 100:.2f}%",
            "none",
            "Fixed rate (Spitzer)",
        )

    fixed_cpi_rate = rate_table.get("fixed_cpi")
    if fixed_cpi_rate is not None:
        add_detail(
            "fixed_cpi",
            shares.fixed_cpi,
            f"{fixed_cpi_rate * 100:.2f}%",
            "cpi",
            "Fixed CPI-indexed",
        )

    variable_unlinked_rate = rate_table.get("variable_unindexed")
    if variable_unlinked_rate is not None:
        margin = variable_unlinked_rate - BASE_ANCHOR_RATES[RateAnchor.GOV_5Y]
        add_detail(
            "variable_unindexed",
            getattr(shares, "variable_unindexed", 0.0),
            _format_margin("Gov5y", margin),
            "none",
            "Resets every 5 years",
        )

    variable_cpi_rate = rate_table.get("variable_cpi")
    if variable_cpi_rate is not None:
        margin = variable_cpi_rate - BASE_ANCHOR_RATES[RateAnchor.GOV_5Y]
        add_detail(
            "variable_cpi",
            shares.variable_cpi,
            _format_margin("Gov5y", margin),
            "cpi",
            "CPI-linked reset every 5 years",
        )

    return details


def _default_rate_table() -> Dict[str, float]:
    rate_table = DEFAULT_TRACK_RATES.copy()
    for track_key, rate in _MENU_TRACK_RATES.items():
        if isinstance(rate, (int, float)) and rate > 0:
            rate_table[track_key] = float(rate)
    return rate_table


_SCENARIO_RATE_SHOCKS: Dict[str, float] = {
    "fall": -0.01,
    "flat": 0.0,
    "rise": 0.02,
}

_STRESS_RATE_SHOCK: float = 0.03

_UNIFORM_BASKETS: List[UniformBasket] = [
    UniformBasket(
        name="Uniform Basket A - Fixed",
        shares=TrackShares(
            fixed_unindexed=1.0,
            fixed_cpi=0.0,
            variable_prime=0.0,
            variable_cpi=0.0,
        ),
    ),
    UniformBasket(
        name="Uniform Basket B - Mixed",
        shares=TrackShares(
            fixed_unindexed=1 / 3,
            fixed_cpi=0.0,
            variable_prime=1 / 3,
            variable_cpi=1 / 3,
        ),
    ),
    UniformBasket(
        name="Uniform Basket C - Fixed & Prime",
        shares=TrackShares(
            fixed_unindexed=0.5,
            fixed_cpi=0.0,
            variable_prime=0.5,
            variable_cpi=0.0,
        ),
    ),
]


def _build_rate_table(interview: InterviewRecord) -> Dict[str, float]:
    rate_table = _default_rate_table()
    quotes = getattr(interview, "quotes", None)
    if quotes:
        for track in quotes.tracks:
            base = BASE_ANCHOR_RATES.get(
                track.rate_anchor, rate_table.get(track.track, 0.04)
            )
            margin = track.margin_pct / 100 if track.margin_pct is not None else 0.0
            rate_table[track.track] = max(base + margin, 0.0)
    return rate_table


def _calculate_monthly_payment(
    loan_amount: float, term_years: int, annual_rate: float
) -> float:
    monthly_rate = max(annual_rate, 0.0) / 12
    months = max(term_years, 1) * 12
    if monthly_rate <= 0:
        return loan_amount / months
    factor = (
        monthly_rate * (1 + monthly_rate) ** months / ((1 + monthly_rate) ** months - 1)
    )
    return loan_amount * factor


def _extract_prepayment_map(planning: PlanningContext) -> Dict[int, float]:
    schedule: Dict[int, float] = {}
    for event in planning.prepayment_schedule or []:
        month = int(event.month)
        if month <= 0:
            continue
        pct = max(0.0, min(event.pct_of_balance, 1.0))
        if pct <= 0:
            continue
        schedule[month] = pct
    return schedule


def _simulate_total_interest(
    loan_amount: float,
    term_years: int,
    annual_rate: float,
    payment: float,
    prepayment_map: Dict[int, float],
) -> float:
    monthly_rate = max(annual_rate, 0.0) / 12
    months = max(term_years, 1) * 12
    balance = loan_amount
    total_interest = 0.0

    for current_month in range(1, months + 1):
        if balance <= 1e-6:
            break

        interest = balance * monthly_rate
        total_interest += interest

        principal_payment = payment - interest
        if principal_payment < 0:
            principal_payment = 0.0
        principal_payment = min(principal_payment, balance)
        balance -= principal_payment

        pct = prepayment_map.get(current_month)
        if pct and balance > 0:
            balance -= balance * pct

        balance = max(balance, 0.0)

    return total_interest


def _compute_metrics(
    loan_amount: float,
    term_years: int,
    net_income: float,
    property_value: float,
    planning: PlanningContext,
    shares: TrackShares,
    rate_table: Dict[str, float],
) -> MixMetrics:
    total_share = max(shares.total(), 1e-6)
    avg_rate = (
        rate_table.get("fixed_unindexed", 0.04) * shares.fixed_unindexed
        + rate_table.get("fixed_cpi", 0.035) * shares.fixed_cpi
        + rate_table.get("variable_prime", 0.045) * shares.variable_prime
        + rate_table.get("variable_cpi", 0.038) * shares.variable_cpi
    ) / total_share

    monthly_payment = _calculate_monthly_payment(loan_amount, term_years, avg_rate)
    base_pti = monthly_payment / max(net_income, 1.0)

    stress_rate = max(avg_rate + _STRESS_RATE_SHOCK, 0.0)
    stress_payment = _calculate_monthly_payment(loan_amount, term_years, stress_rate)

    scenario_weights = {}
    weights_model = getattr(planning, "scenario_weights", None)
    if weights_model is not None:
        scenario_weights = {
            "fall": getattr(weights_model, "fall", 0.0),
            "flat": getattr(weights_model, "flat", 0.0),
            "rise": getattr(weights_model, "rise", 0.0),
        }
    else:
        scenario_weights = {"fall": 0.2, "flat": 0.6, "rise": 0.2}

    scenario_payments: Dict[str, float] = {}
    for name, shock in _SCENARIO_RATE_SHOCKS.items():
        rate = max(avg_rate + shock, 0.0)
        scenario_payments[name] = _calculate_monthly_payment(
            loan_amount, term_years, rate
        )

    total_weight = sum(scenario_weights.values())
    if total_weight > 0:
        expected_weighted_payment = (
            sum(
                scenario_weights[name] * scenario_payments.get(name, monthly_payment)
                for name in scenario_weights
            )
            / total_weight
        )
    else:
        expected_weighted_payment = monthly_payment

    highest_expected_payment = max(
        [monthly_payment, stress_payment, *scenario_payments.values()]
    )

    months = max(term_years * 12, 1)
    peak_pti = highest_expected_payment / max(net_income, 1.0)
    variable_share_pct = (shares.variable_prime + shares.variable_cpi) * 100
    cpi_share_pct = (shares.fixed_cpi + shares.variable_cpi) * 100
    ltv_ratio = (loan_amount / property_value) if property_value > 0 else 0.0
    five_year_cost = expected_weighted_payment * min(months, 60)
    total_weighted_cost = expected_weighted_payment * months

    prepayment_map = _extract_prepayment_map(planning)
    total_interest = _simulate_total_interest(
        loan_amount,
        term_years,
        avg_rate,
        monthly_payment,
        prepayment_map,
    )

    prepayment_exposure = _estimate_prepayment_exposure(shares)
    track_details = _build_track_details(shares, loan_amount, rate_table)

    return MixMetrics(
        monthly_payment_nis=monthly_payment,
        pti_ratio=base_pti,
        pti_ratio_peak=peak_pti,
        total_interest_paid=total_interest,
        max_payment_under_stress=stress_payment,
        average_rate_pct=avg_rate * 100,
        expected_weighted_payment_nis=expected_weighted_payment,
        highest_expected_payment_nis=highest_expected_payment,
        five_year_cost_nis=five_year_cost,
        total_weighted_cost_nis=total_weighted_cost,
        variable_share_pct=variable_share_pct,
        cpi_share_pct=cpi_share_pct,
        ltv_ratio=ltv_ratio,
        prepayment_fee_exposure=prepayment_exposure,
        track_details=track_details,
    )


def _score_candidate(
    candidate: OptimizationCandidate, planning: PlanningContext
) -> float:
    weights = planning.weights
    metrics = candidate.metrics
    return (
        weights.expected_cost * metrics.expected_weighted_payment_nis
        + weights.payment_volatility * metrics.highest_expected_payment_nis
        + weights.cpi_exposure * candidate.shares.fixed_cpi
        + weights.prepay_fee_exposure * candidate.shares.fixed_unindexed
        + (metrics.average_rate_pct / 100)
    )


def _build_recommended_candidate(
    interview: InterviewRecord, planning: PlanningContext, rate_table: Dict[str, float]
) -> OptimizationCandidate:
    loan_amount = interview.loan.amount_nis
    term_years = interview.loan.term_years
    income = interview.borrower.net_income_nis
    existing_loans = interview.borrower.fixed_expenses_nis
    property_value = interview.property.value_nis

    variable_cap = min(planning.soft_caps.variable_share_max, 0.66)
    cpi_cap = planning.soft_caps.cpi_share_max

    variable_cpi = min(variable_cap, cpi_cap * 0.5)
    variable_prime = max(variable_cap - variable_cpi, 0.0)

    fixed_remaining = max(1.0 - (variable_prime + variable_cpi), 0.0)
    fixed_cpi = min(cpi_cap - variable_cpi, max(fixed_remaining * 0.25, 0.0))
    fixed_unindexed = max(1.0 - (variable_prime + variable_cpi + fixed_cpi), 0.0)

    shares = TrackShares(
        fixed_unindexed=fixed_unindexed,
        fixed_cpi=max(fixed_cpi, 0.0),
        variable_prime=variable_prime,
        variable_cpi=variable_cpi,
    )

    metrics = _compute_metrics(
        loan_amount, term_years, income, property_value, planning, shares, rate_table
    )
    feasibility = run_feasibility_checks(
        property_price=interview.property.value_nis,
        down_payment_available=interview.property.value_nis - loan_amount,
        monthly_net_income=income,
        existing_monthly_loans=existing_loans,
        loan_years=term_years,
        property_type=interview.property.type.value,
    )

    notes: List[str] = []
    if feasibility.issues:
        notes.append("Mix requires adjustments to meet BOI limits.")

    return OptimizationCandidate(
        label="Customized mix",
        shares=shares,
        metrics=metrics,
        feasibility=feasibility,
        notes=notes,
    )


def optimize_mixes(
    interview: InterviewRecord,
    planning: PlanningContext,
) -> OptimizationResult:
    loan_amount = interview.loan.amount_nis
    term_years = interview.loan.term_years
    net_income = interview.borrower.net_income_nis
    fixed_expenses = interview.borrower.fixed_expenses_nis
    property_value = interview.property.value_nis

    rate_table = _build_rate_table(interview)

    candidates: List[OptimizationCandidate] = []

    for basket in _UNIFORM_BASKETS:
        metrics = _compute_metrics(
            loan_amount,
            term_years,
            net_income,
            property_value,
            planning,
            basket.shares,
            rate_table,
        )
        feasibility = run_feasibility_checks(
            property_price=interview.property.value_nis,
            down_payment_available=interview.property.value_nis - loan_amount,
            monthly_net_income=net_income,
            existing_monthly_loans=fixed_expenses,
            loan_years=term_years,
            property_type=interview.property.type.value,
        )
        candidates.append(
            OptimizationCandidate(
                label=basket.name,
                shares=basket.shares,
                metrics=metrics,
                feasibility=feasibility,
                notes=[],
            )
        )

    recommended = _build_recommended_candidate(interview, planning, rate_table)
    candidates.append(recommended)

    scores = [_score_candidate(c, planning) for c in candidates]
    recommended_index = min(range(len(scores)), key=scores.__getitem__)

    assumptions = {
        "loan_amount": loan_amount,
        "term_years": term_years,
        "net_income": net_income,
        "existing_loans": fixed_expenses,
    }

    return OptimizationResult(
        candidates=candidates,
        recommended_index=recommended_index,
        assumptions=assumptions,
    )
