from typing import Any, TypedDict
import pytest

from app.domain.schemas import Preferences, RateView


class PreferencesDict(TypedDict, total=False):
    stability_vs_cost: int
    cpi_tolerance: int | None
    prime_exposure_preference: int | None
    max_payment_nis: float | int | None
    red_line_payment_nis: float | int | None
    expected_prepay_pct: float
    expected_prepay_month: int | None
    prepayment_confirmed: bool
    rate_view: RateView
    additional_signals: list[Any]


def _build_preferences(**overrides: Any) -> Preferences:
    base: PreferencesDict = {
        "stability_vs_cost": 5,
        "cpi_tolerance": 6,
        "prime_exposure_preference": 4,
        "max_payment_nis": 6_500,
        "red_line_payment_nis": 7_500,
        "expected_prepay_pct": 0.0,
        "expected_prepay_month": None,
        "prepayment_confirmed": False,
        "rate_view": RateView.FLAT,
        "additional_signals": [],
    }
    merged = {**base, **overrides}
    return Preferences(**merged)


def test_preferences_rejects_currency_strings():
    with pytest.raises(TypeError):
        _build_preferences(
            max_payment_nis="6,500",
            red_line_payment_nis="7.2k",
        )


def test_preferences_rejects_range_string():
    with pytest.raises(TypeError):
        _build_preferences(
            max_payment_nis="5.5k-6.5k",
            red_line_payment_nis="5.5k-6.5k",
        )


def test_preferences_rejects_too_small_payment():
    with pytest.raises(ValueError):
        _build_preferences(max_payment_nis=0.5, red_line_payment_nis=0.6)


def test_preferences_allow_missing_payments():
    prefs = _build_preferences(max_payment_nis=None, red_line_payment_nis=None)
    assert prefs.max_payment_nis is None
    assert prefs.red_line_payment_nis is None


def test_preferences_accept_blank_string_as_missing():
    prefs = _build_preferences(max_payment_nis="  ", red_line_payment_nis="")
    assert prefs.max_payment_nis is None
    assert prefs.red_line_payment_nis is None
