"""Mix optimization utilities for mortgage compositions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from app.configuration.menu_loader import load_average_menu_rates
from app.domain.schemas import (
    InterviewRecord,
    MixMetrics,
    OptimizationCandidate,
    OptimizationResult,
    PlanningContext,
    RateAnchor,
    TermSweepEntry,
    TrackShares,
    TrackDetail,
    PaymentSensitivity,
)
from app.configuration import boi_limits
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
        track: str,
        share: float,
        rate_display: str,
        indexation: str,
        reset_note: str,
        anchor_rate_pct: float | None = None,
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
                anchor_rate_pct=anchor_rate_pct,
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
            BASE_ANCHOR_RATES[RateAnchor.PRIME] * 100,
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
            None,
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
            BASE_ANCHOR_RATES[RateAnchor.GOV_5Y] * 100,
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

SENSITIVITY_SHOCKS: List[Tuple[str, Dict[str, float]]] = [
    ("prime_+1pct", {"variable_prime": 0.01}),
    ("prime_+2pct", {"variable_prime": 0.02}),
    ("prime_+3pct", {"variable_prime": 0.03}),
    ("cpi_path_+2pct", {"fixed_cpi": 0.02, "variable_cpi": 0.02}),
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


def _mix_payment(
    loan_amount: float,
    term_years: int,
    shares: TrackShares,
    rate_table: Dict[str, float],
    adjustments: Dict[str, float] | None = None,
) -> Tuple[float, Dict[str, float]]:
    adjustments = adjustments or {}
    payments: Dict[str, float] = {}
    total_payment = 0.0

    for track_key, share in (
        ("fixed_unindexed", shares.fixed_unindexed),
        ("fixed_cpi", shares.fixed_cpi),
        ("variable_prime", shares.variable_prime),
        ("variable_cpi", shares.variable_cpi),
    ):
        if share <= 0:
            continue
        amount = loan_amount * share
        base_rate = rate_table.get(track_key, DEFAULT_TRACK_RATES.get(track_key, 0.0))
        rate_delta = adjustments.get(track_key, 0.0)
        payment = _calculate_monthly_payment(
            amount, term_years, max(base_rate + rate_delta, 0.0)
        )
        payments[track_key] = payment
        total_payment += payment

    return total_payment, payments


def _floating_rate_adjustments(shock: float) -> Dict[str, float]:
    if abs(shock) <= 1e-9:
        return {}
    adjustments = {
        "variable_prime": shock,
        "variable_cpi": shock,
    }
    adjustments["fixed_cpi"] = shock
    return adjustments


def _soft_cap_notes(
    planning: PlanningContext, shares: TrackShares, metrics: MixMetrics
) -> List[str]:
    notes: List[str] = []
    caps = planning.soft_caps

    variable_share = shares.variable_prime + shares.variable_cpi
    if variable_share > caps.variable_share_max + 1e-6:
        notes.append(
            f"Variable exposure {variable_share * 100:.1f}% exceeds comfort cap {caps.variable_share_max * 100:.0f}%."
        )

    cpi_share = shares.fixed_cpi + shares.variable_cpi
    if caps.cpi_share_max is not None and cpi_share > caps.cpi_share_max + 1e-6:
        notes.append(
            f"CPI exposure {cpi_share * 100:.1f}% exceeds comfort cap {caps.cpi_share_max * 100:.0f}%."
        )

    if metrics.future_pti_breach:
        month_desc = (
            f"month {metrics.future_pti_month}"
            if metrics.future_pti_month is not None
            else "a future month"
        )
        if metrics.future_pti_target is not None:
            notes.append(
                f"Projected PTI in {month_desc} exceeds comfort target ({metrics.future_pti_target * 100:.0f}%)."
            )
        elif metrics.future_pti_ratio is not None:
            notes.append(
                f"Projected PTI in {month_desc} rises to {metrics.future_pti_ratio * 100:.1f}%."
            )

    payment_ceiling = caps.payment_ceiling_nis
    if (
        payment_ceiling is not None
        and metrics.highest_expected_payment_nis > payment_ceiling + 1e-6
    ):
        notes.append(
            "Peak payment ₪{peak:,.0f} exceeds the agreed stress ceiling ₪{ceiling:,.0f}.".format(
                peak=metrics.highest_expected_payment_nis,
                ceiling=payment_ceiling,
            )
        )

    return notes


def _compute_metrics(
    loan_amount: float,
    term_years: int,
    net_income: float,
    existing_obligations: float,
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

    monthly_payment, _ = _mix_payment(
        loan_amount, term_years, shares, rate_table, adjustments=None
    )
    obligations = max(existing_obligations, 0.0)
    income = max(net_income, 1.0)
    base_pti = (monthly_payment + obligations) / income

    assumptions = getattr(planning, "metadata", {}).get("assumptions", {}) or {}
    baseline_income_total = assumptions.get("baseline_income", net_income)
    baseline_expense_total = assumptions.get("baseline_expense", existing_obligations)

    income_timeline = getattr(planning, "income_timeline", []) or []
    expense_timeline = getattr(planning, "expense_timeline", []) or []
    pti_targets = getattr(planning, "pti_targets", []) or []

    future_pti_ratio = None
    future_pti_month = None
    future_pti_target = None
    future_pti_breach = False

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
        adjustments = _floating_rate_adjustments(shock)
        payment, _ = _mix_payment(
            loan_amount, term_years, shares, rate_table, adjustments
        )
        scenario_payments[name] = payment

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

    sensitivity_entries: List[PaymentSensitivity] = []
    sensitivity_payments: Dict[str, float] = {}
    for label, adjustments in SENSITIVITY_SHOCKS:
        payment, _ = _mix_payment(
            loan_amount, term_years, shares, rate_table, adjustments
        )
        sensitivity_entries.append(
            PaymentSensitivity(
                scenario=label,
                payment_nis=payment,
            )
        )
        sensitivity_payments[label] = payment

    stress_payment = monthly_payment
    if sensitivity_payments:
        stress_payment = max(stress_payment, *sensitivity_payments.values())

    highest_expected_payment = monthly_payment
    peak_payment_driver = "base"
    peak_payment_month = 1
    months = max(term_years * 12, 1)

    def _update_peak(candidate_payment: float, driver: str, month: int) -> None:
        nonlocal highest_expected_payment, peak_payment_driver, peak_payment_month
        if candidate_payment > highest_expected_payment + 1e-6:
            highest_expected_payment = candidate_payment
            peak_payment_driver = driver
            peak_payment_month = month

    for name, payment in scenario_payments.items():
        _update_peak(payment, f"scenario_{name}", min(months, 60))

    for label, payment in sensitivity_payments.items():
        _update_peak(payment, f"sensitivity_{label}", 1)

    _update_peak(stress_payment, "stress_prime", 1)

    horizon = min(len(income_timeline), len(expense_timeline))
    if horizon:
        baseline_income_total = (
            baseline_income_total if baseline_income_total is not None else net_income
        )
        baseline_expense_total = (
            baseline_expense_total
            if baseline_expense_total is not None
            else existing_obligations
        )
        for month in range(horizon):
            income_adjustment = income_timeline[month] - baseline_income_total
            expense_adjustment = expense_timeline[month] - baseline_expense_total
            future_net_income = max(net_income + income_adjustment, 1.0)
            future_obligations = max(obligations + expense_adjustment, 0.0)
            future_pti = (monthly_payment + future_obligations) / future_net_income
            target = None
            if month < len(pti_targets):
                target = pti_targets[month]
            if future_pti_ratio is None or future_pti > future_pti_ratio + 1e-6:
                future_pti_ratio = future_pti
                future_pti_month = month + 1
                future_pti_target = target
            if target is not None and future_pti > target + 1e-6:
                future_pti_breach = True

    if peak_payment_driver.startswith("scenario"):
        highest_expected_payment_note = "Peak payment reflects the Bank of Israel disclosure path (Prime +3% / CPI +2%)."
    elif peak_payment_driver.startswith("sensitivity_prime_"):
        highest_expected_payment_note = (
            "Peak payment assumes an immediate prime shock "
            f"{peak_payment_driver.split('_')[-1]} from the disclosure sensitivity."
        )
    elif peak_payment_driver == "stress_prime":
        highest_expected_payment_note = (
            "Peak payment equals the disclosed stress payment (Prime +3%)."
        )
    else:
        highest_expected_payment_note = (
            "Peak payment matches the base scenario with no rate shocks."
        )

    peak_pti = (highest_expected_payment + obligations) / income
    pti_ratio_peak_month = peak_payment_month
    if future_pti_ratio is not None and future_pti_ratio > peak_pti + 1e-6:
        peak_pti = future_pti_ratio
        pti_ratio_peak_month = future_pti_month
    variable_share_pct = (shares.variable_prime + shares.variable_cpi) * 100
    cpi_share_pct = (shares.fixed_cpi + shares.variable_cpi) * 100
    ltv_ratio = (loan_amount / property_value) if property_value > 0 else 0.0
    five_year_total_payment = expected_weighted_payment * min(months, 60)
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
        pti_ratio_peak_month=pti_ratio_peak_month,
        total_interest_paid=total_interest,
        max_payment_under_stress=stress_payment,
        average_rate_pct=avg_rate * 100,
        expected_weighted_payment_nis=expected_weighted_payment,
        highest_expected_payment_nis=highest_expected_payment,
        highest_expected_payment_note=highest_expected_payment_note,
        peak_payment_month=peak_payment_month,
        peak_payment_driver=peak_payment_driver,
        five_year_total_payment_nis=five_year_total_payment,
        total_weighted_cost_nis=total_weighted_cost,
        variable_share_pct=variable_share_pct,
        cpi_share_pct=cpi_share_pct,
        ltv_ratio=ltv_ratio,
        prepayment_fee_exposure=prepayment_exposure,
        track_details=track_details,
        payment_sensitivity=sensitivity_entries,
        future_pti_ratio=future_pti_ratio,
        future_pti_month=future_pti_month,
        future_pti_target=future_pti_target,
        future_pti_breach=future_pti_breach,
    )


def _build_term_sweep(
    loan_amount: float,
    net_income: float,
    existing_obligations: float,
    property_value: float,
    planning: PlanningContext,
    shares: TrackShares,
    rate_table: Dict[str, float],
    base_term_years: int,
    base_metrics: MixMetrics,
) -> List[TermSweepEntry]:
    candidate_terms = {15, 20, 25, base_term_years}
    sweep_terms = sorted(term for term in candidate_terms if 5 <= term <= 30)
    entries: List[TermSweepEntry] = []
    for term in sweep_terms:
        if term == base_term_years:
            metrics = base_metrics
        else:
            metrics = _compute_metrics(
                loan_amount,
                term,
                net_income,
                existing_obligations,
                property_value,
                planning,
                shares,
                rate_table,
            )
        entries.append(
            TermSweepEntry(
                term_years=term,
                monthly_payment_nis=metrics.monthly_payment_nis,
                stress_payment_nis=metrics.max_payment_under_stress,
                expected_weighted_payment_nis=metrics.expected_weighted_payment_nis,
                pti_ratio=metrics.pti_ratio,
                pti_ratio_peak=metrics.pti_ratio_peak,
            )
        )
    return entries


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


def _assemble_candidate(
    label: str,
    shares: TrackShares,
    interview: InterviewRecord,
    planning: PlanningContext,
    rate_table: Dict[str, float],
) -> OptimizationCandidate:
    loan_amount = interview.loan.amount_nis
    term_years = interview.loan.term_years
    net_income = interview.borrower.net_income_nis
    fixed_expenses = interview.borrower.fixed_expenses_nis
    property_value = interview.property.value_nis
    other_housing = interview.borrower.other_housing_payments_nis
    rent_expense = interview.borrower.rent_expense_nis
    bridge_term_months = interview.loan.bridge_term_months
    any_purpose_amount = interview.loan.any_purpose_amount_nis
    property_appraisal = interview.property.appraisal_value_nis

    metrics = _compute_metrics(
        loan_amount,
        term_years,
        net_income,
        fixed_expenses,
        property_value,
        planning,
        shares,
        rate_table,
    )
    feasibility = run_feasibility_checks(
        property_price=interview.property.value_nis,
        down_payment_available=interview.property.value_nis - loan_amount,
        monthly_net_income=net_income,
        existing_monthly_loans=fixed_expenses,
        loan_years=term_years,
        property_type=interview.property.type.value,
        deal_type=interview.deal_type.value,
        occupancy=interview.borrower.occupancy.value,
        assessed_payment=metrics.monthly_payment_nis,
        peak_payment=metrics.highest_expected_payment_nis,
        borrower_age_years=interview.borrower.age_years,
        variable_share=shares.variable_prime + shares.variable_cpi,
        other_housing_payments=other_housing,
        borrower_rent_expense=rent_expense,
        is_bridge_loan=interview.loan.is_bridge_loan,
        bridge_term_months=bridge_term_months,
        any_purpose_amount_nis=any_purpose_amount,
        is_reduced_price_dwelling=interview.property.is_reduced_price_dwelling,
        appraised_value_nis=property_appraisal,
        is_refinance=interview.loan.is_refinance,
        previous_pti_ratio=interview.loan.previous_pti_ratio,
        previous_ltv_ratio=interview.loan.previous_ltv_ratio,
        previous_variable_share_ratio=interview.loan.previous_variable_share_ratio,
    )
    notes = _soft_cap_notes(planning, shares, metrics)
    if feasibility.issues:
        warning = "Mix requires adjustments to meet BOI limits."
        if warning not in notes:
            notes.append(warning)

    return OptimizationCandidate(
        label=label,
        shares=shares,
        metrics=metrics,
        feasibility=feasibility,
        notes=notes,
    )


def _compose_shares(
    variable_prime: float,
    variable_cpi: float,
    fixed_cpi: float,
    planning: PlanningContext,
) -> TrackShares:
    variable_prime = max(variable_prime, 0.0)
    variable_cpi = max(variable_cpi, 0.0)
    fixed_cpi = max(fixed_cpi, 0.0)

    variable_cap = min(
        planning.soft_caps.variable_share_max, boi_limits.VARIABLE_SHARE_LIMIT
    )
    variable_total = variable_prime + variable_cpi
    if variable_total > variable_cap + 1e-6:
        scale = variable_cap / variable_total if variable_total > 0 else 0.0
        variable_prime *= scale
        variable_cpi *= scale
        variable_total = variable_cap

    cpi_cap = planning.soft_caps.cpi_share_max
    if cpi_cap is not None:
        total_cpi = variable_cpi + fixed_cpi
        if total_cpi > cpi_cap + 1e-6:
            excess = total_cpi - cpi_cap
            reduction = min(fixed_cpi, excess)
            fixed_cpi -= reduction
            excess -= reduction
            if excess > 0:
                reduction = min(variable_cpi, excess)
                variable_cpi -= reduction
                excess -= reduction
            fixed_cpi = max(fixed_cpi, 0.0)
            variable_cpi = max(variable_cpi, 0.0)

    variable_prime = max(variable_prime, 0.0)
    variable_cpi = max(variable_cpi, 0.0)
    fixed_cpi = max(fixed_cpi, 0.0)

    total = variable_prime + variable_cpi + fixed_cpi
    if total > 1.0 + 1e-6:
        scale = 1.0 / total if total > 0 else 0.0
        variable_prime *= scale
        variable_cpi *= scale
        fixed_cpi *= scale
        total = variable_prime + variable_cpi + fixed_cpi

    fixed_unindexed = max(1.0 - total, 0.0)
    total = variable_prime + variable_cpi + fixed_cpi + fixed_unindexed
    if abs(total - 1.0) > 1e-6:
        fixed_unindexed += 1.0 - total
        fixed_unindexed = max(fixed_unindexed, 0.0)

    return TrackShares(
        fixed_unindexed=fixed_unindexed,
        fixed_cpi=fixed_cpi,
        variable_prime=variable_prime,
        variable_cpi=variable_cpi,
    )


def _generate_balanced_shares(planning: PlanningContext) -> TrackShares:
    variable_cap = min(
        planning.soft_caps.variable_share_max, boi_limits.VARIABLE_SHARE_LIMIT
    )
    cpi_cap = planning.soft_caps.cpi_share_max
    effective_cpi_cap = cpi_cap if cpi_cap is not None else 1.0

    variable_cpi = min(variable_cap, effective_cpi_cap * 0.5)
    variable_prime = max(variable_cap - variable_cpi, 0.0)
    fixed_remaining = max(1.0 - (variable_prime + variable_cpi), 0.0)

    if cpi_cap is not None:
        max_fixed_cpi = max(cpi_cap - variable_cpi, 0.0)
        fixed_cpi = min(max_fixed_cpi, fixed_remaining * 0.25)
    else:
        fixed_cpi = fixed_remaining * 0.25

    return _compose_shares(variable_prime, variable_cpi, fixed_cpi, planning)


def _generate_stability_shares(
    planning: PlanningContext, base_shares: TrackShares
) -> TrackShares:
    base_variable = base_shares.variable_prime + base_shares.variable_cpi
    reduction = min(0.1, base_variable)
    target_variable = max(base_variable - reduction, 0.05)
    target_variable = min(target_variable, planning.soft_caps.variable_share_max)

    ratio_prime = (
        base_shares.variable_prime / base_variable if base_variable > 1e-6 else 0.6
    )
    ratio_prime = min(max(ratio_prime, 0.3), 0.8)
    variable_prime = target_variable * ratio_prime
    variable_cpi = max(target_variable - variable_prime, 0.0)

    if planning.soft_caps.cpi_share_max is not None:
        max_fixed_cpi = max(planning.soft_caps.cpi_share_max - variable_cpi, 0.0)
        fixed_cpi_target = min(base_shares.fixed_cpi + reduction * 0.5, max_fixed_cpi)
    else:
        fixed_cpi_target = min(base_shares.fixed_cpi + reduction * 0.5, 0.25)

    return _compose_shares(variable_prime, variable_cpi, fixed_cpi_target, planning)


def _generate_low_payment_shares(
    planning: PlanningContext, base_shares: TrackShares
) -> TrackShares:
    base_variable = base_shares.variable_prime + base_shares.variable_cpi
    headroom = max(planning.soft_caps.variable_share_max - base_variable, 0.0)
    increase = min(0.1, headroom)
    target_variable = min(
        base_variable + increase, planning.soft_caps.variable_share_max
    )

    ratio_prime = (
        base_shares.variable_prime / base_variable if base_variable > 1e-6 else 0.6
    )
    ratio_prime = min(max(ratio_prime + 0.1, 0.4), 0.9)
    variable_prime = min(target_variable * ratio_prime, target_variable)
    variable_cpi = max(target_variable - variable_prime, 0.0)

    fixed_cpi_target = max(base_shares.fixed_cpi - increase * 0.5, 0.0)

    return _compose_shares(variable_prime, variable_cpi, fixed_cpi_target, planning)


def _shares_are_close(left: TrackShares, right: TrackShares, tol: float = 1e-3) -> bool:
    return (
        abs(left.fixed_unindexed - right.fixed_unindexed) <= tol
        and abs(left.fixed_cpi - right.fixed_cpi) <= tol
        and abs(left.variable_prime - right.variable_prime) <= tol
        and abs(left.variable_cpi - right.variable_cpi) <= tol
    )


def _build_personalized_candidate(
    interview: InterviewRecord,
    planning: PlanningContext,
    rate_table: Dict[str, float],
    label: str,
    shares: TrackShares,
) -> OptimizationCandidate:
    return _assemble_candidate(
        label=label,
        shares=shares,
        interview=interview,
        planning=planning,
        rate_table=rate_table,
    )


def _select_candidate_indices(
    candidates: List[OptimizationCandidate],
    planning: PlanningContext,
) -> Tuple[int, int, int]:
    scores = [_score_candidate(candidate, planning) for candidate in candidates]
    engine_recommended_index = min(range(len(scores)), key=scores.__getitem__)

    def _violates_soft_caps(candidate: OptimizationCandidate) -> bool:
        for note in candidate.notes:
            lowered = note.lower()
            if "exceeds comfort cap" in lowered or "exceeds comfort ceiling" in lowered:
                return True
        feasibility = candidate.feasibility
        if feasibility and feasibility.issues:
            illegal_codes = {
                "variable_share_exceeds_limit",
                "loan_term_exceeds_limit",
            }
            if any(issue.code in illegal_codes for issue in feasibility.issues):
                return True
        return False

    advisor_candidates = [
        idx
        for idx, candidate in enumerate(candidates)
        if not _violates_soft_caps(candidate)
    ]

    if advisor_candidates:
        advisor_recommended_index = min(advisor_candidates, key=lambda idx: scores[idx])
    else:
        advisor_recommended_index = engine_recommended_index

    recommended_index = advisor_recommended_index
    return engine_recommended_index, advisor_recommended_index, recommended_index


def _compute_pareto_alerts(
    candidates: List[OptimizationCandidate], recommended_index: int
) -> List[str]:
    def _dominates(left: OptimizationCandidate, right: OptimizationCandidate) -> bool:
        lm, rm = left.metrics, right.metrics
        return (
            lm.monthly_payment_nis <= rm.monthly_payment_nis + 1e-6
            and lm.highest_expected_payment_nis
            <= rm.highest_expected_payment_nis + 1e-6
            and (
                lm.monthly_payment_nis < rm.monthly_payment_nis - 1e-6
                or lm.highest_expected_payment_nis
                < rm.highest_expected_payment_nis - 1e-6
            )
        )

    recommended_candidate = candidates[recommended_index]
    pareto_alerts: List[str] = []
    for idx, candidate in enumerate(candidates):
        if idx == recommended_index:
            continue
        if _dominates(candidate, recommended_candidate):
            pareto_alerts.append(
                f"{candidate.label} dominates recommended mix on opening and peak payments."
            )
    return pareto_alerts


def _build_assumptions(
    interview: InterviewRecord,
    planning: PlanningContext,
    rate_table: Dict[str, float],
    advisor_candidate: OptimizationCandidate,
    candidates: List[OptimizationCandidate],
    recommended_index: int,
) -> Dict[str, Any]:
    loan_amount = interview.loan.amount_nis
    term_years = interview.loan.term_years
    net_income = interview.borrower.net_income_nis
    fixed_expenses = interview.borrower.fixed_expenses_nis

    assumptions: Dict[str, Any] = {
        "loan_amount": loan_amount,
        "term_years": term_years,
        "net_income": net_income,
        "existing_loans": fixed_expenses,
    }

    anchor_rates_pct = {
        anchor.value: BASE_ANCHOR_RATES[anchor] * 100 for anchor in BASE_ANCHOR_RATES
    }
    rate_table_snapshot_pct = {key: value * 100 for key, value in rate_table.items()}
    assumptions.update(
        {
            "anchor_rates_pct": anchor_rates_pct,
            "rate_table_snapshot_pct": rate_table_snapshot_pct,
            "rate_table_captured_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    assumptions["pareto_alerts"] = _compute_pareto_alerts(candidates, recommended_index)
    assumptions["advisor_recommendation_label"] = advisor_candidate.label

    return assumptions


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

    personalized_candidates: List[OptimizationCandidate] = []

    balanced_shares = _generate_balanced_shares(planning)
    balanced_candidate = _build_personalized_candidate(
        interview=interview,
        planning=planning,
        rate_table=rate_table,
        label="Tailored Mix – Balanced",
        shares=balanced_shares,
    )
    personalized_candidates.append(balanced_candidate)

    stability_shares = _generate_stability_shares(planning, balanced_shares)
    if not _shares_are_close(stability_shares, balanced_shares):
        personalized_candidates.append(
            _build_personalized_candidate(
                interview=interview,
                planning=planning,
                rate_table=rate_table,
                label="Tailored Mix – Stability",
                shares=stability_shares,
            )
        )

    low_payment_shares = _generate_low_payment_shares(planning, balanced_shares)
    if all(
        not _shares_are_close(low_payment_shares, candidate.shares)
        for candidate in personalized_candidates
    ):
        personalized_candidates.append(
            _build_personalized_candidate(
                interview=interview,
                planning=planning,
                rate_table=rate_table,
                label="Tailored Mix – Low Payment",
                shares=low_payment_shares,
            )
        )

    candidates: List[OptimizationCandidate] = personalized_candidates

    (
        engine_recommended_index,
        advisor_recommended_index,
        recommended_index,
    ) = _select_candidate_indices(candidates, planning)

    advisor_candidate = candidates[advisor_recommended_index]
    term_sweep = _build_term_sweep(
        loan_amount=loan_amount,
        net_income=net_income,
        existing_obligations=fixed_expenses,
        property_value=property_value,
        planning=planning,
        shares=advisor_candidate.shares,
        rate_table=rate_table,
        base_term_years=term_years,
        base_metrics=advisor_candidate.metrics,
    )

    assumptions = _build_assumptions(
        interview=interview,
        planning=planning,
        rate_table=rate_table,
        advisor_candidate=advisor_candidate,
        candidates=candidates,
        recommended_index=recommended_index,
    )

    return OptimizationResult(
        candidates=candidates,
        recommended_index=recommended_index,
        engine_recommended_index=engine_recommended_index,
        advisor_recommended_index=advisor_recommended_index,
        term_sweep=term_sweep,
        assumptions=assumptions,
    )
