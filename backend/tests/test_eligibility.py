"""可算性校验单测：窗口完整性（零销量 vs 缺日）、三类隔离原因、对照充足性。"""
from __future__ import annotations

from datetime import date, timedelta

from src.services import eligibility

START = date(2026, 9, 1)
EVENT = {
    "id": 1,
    "event_no": "PE-2601",
    "channel": "hypermarket",
    "base_price": 12.8,
    "promo_price": 11.65,
    "discount": 0.09,
    "start_on": START,
    "end_on": START + timedelta(days=6),
    "kind": "discount",
}


def _window(
    qty: float = 100.0,
    *,
    lo: date = START - timedelta(days=14),
    hi: date = START + timedelta(days=6),
    event: dict | None = None,
):
    """完整窗口：活动前按牌价、活动窗按促销价（与真实回传一致）。"""
    event = event or EVENT
    series = {}
    day = lo
    while day <= hi:
        in_window = event["start_on"] <= day <= event["end_on"]
        series[day] = {
            "qty": qty,
            "price": event["promo_price"] if in_window else event["base_price"],
            "is_promo": in_window,
        }
        day += timedelta(days=1)
    return series


def _controls(qty: float = 50.0, codes=("A3", "A4", "A6")):
    return {code: _window(qty) for code in codes}


def _assess(treat, controls, *, excluded=(), pre_days=14, event=None):
    live = event or EVENT
    return eligibility.assess(
        event=live,
        treat_series=treat,
        control_series=controls,
        excluded_control_codes=excluded,
        pre_days=pre_days,
        post_days=(live["end_on"] - live["start_on"]).days + 1,
    )


def test_complete_window_is_calculable():
    treat = _window()
    for day in (START, START + timedelta(days=3)):
        treat[day] = {"qty": 118, "price": EVENT["promo_price"], "is_promo": True}
    result = _assess(treat, _controls())
    assert result["calculable"] is True
    assert result["reason"] == ""
    assert all(check["ok"] for check in result["checks"])


def test_zero_qty_is_a_real_observation_not_a_missing_day():
    treat = _window()
    treat[START + timedelta(days=2)]["qty"] = 0
    result = _assess(treat, _controls())
    assert result["calculable"] is True
    assert result["detail"]["missing_days"]["total"] == 0


def test_missing_day_on_treat_is_isolated_with_reason():
    treat = _window()
    del treat[START + timedelta(days=4)]
    result = _assess(treat, _controls())
    assert result["calculable"] is False
    assert result["reason"] == "missing_days"
    assert result["detail"]["missing_days"]["treat"] == [(START + timedelta(days=4)).isoformat()]
    assert result["detail"]["missing_days"]["total"] == 1


def test_missing_day_on_control_is_isolated():
    controls = _controls()
    del controls["A4"][START]
    result = _assess(_window(), controls)
    assert result["calculable"] is False
    assert result["reason"] == "missing_days"
    assert result["detail"]["missing_days"]["controls"]["A4"] == [START.isoformat()]


def test_insufficient_controls_is_isolated():
    result = _assess(_window(), _controls(codes=("A3", "A4")), excluded=["A6"])
    assert result["calculable"] is False
    assert result["reason"] == "insufficient_controls"
    assert result["detail"]["control_count"] == 2
    assert result["detail"]["excluded_controls"] == ["A6"]


def test_price_anomaly_on_promo_day_is_isolated():
    treat = _window()
    treat[START + timedelta(days=1)] = {"qty": 118, "price": EVENT["promo_price"] * 1.1, "is_promo": True}
    result = _assess(treat, _controls())
    assert result["calculable"] is False
    assert result["reason"] == "price_anomaly"
    assert len(result["detail"]["price_issues"]) == 1


def test_invalid_promo_price_is_isolated():
    bad = dict(EVENT, promo_price=13.5)
    result = _assess(_window(event=bad), _controls(), event=bad)
    assert result["calculable"] is False
    assert result["reason"] == "price_anomaly"


def test_zero_pre_window_cannot_build_counterfactual():
    treat = _window()
    for offset in range(1, 15):
        treat[START - timedelta(days=offset)]["qty"] = 0
    result = _assess(treat, _controls())
    assert result["calculable"] is False
    assert result["reason"] == "not_calculable"


def test_short_post_window_is_not_calculable():
    event = dict(EVENT, end_on=EVENT["start_on"] + timedelta(days=1))
    result = _assess(_window(event=event), _controls(), event=event)
    assert result["calculable"] is False
    assert result["reason"] == "not_calculable"


def test_missing_day_takes_priority_over_controls():
    treat = _window()
    del treat[START]
    result = _assess(treat, _controls(codes=("A3",)))
    assert result["reason"] == "missing_days"
