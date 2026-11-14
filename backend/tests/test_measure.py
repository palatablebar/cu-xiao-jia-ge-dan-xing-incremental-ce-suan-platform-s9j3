"""装配层单测：对照 SKU 匹配规则 + 一场活动的端到端增量。"""
from __future__ import annotations

from datetime import date, timedelta

from src.services import measure

START = date(2026, 9, 1)


def _series(values: list[float], start: date, price: float = 12.8, promo: bool = False):
    return {
        start + timedelta(days=index): {"qty": value, "price": price, "is_promo": promo}
        for index, value in enumerate(values)
    }


def _index(length: int = 60, base: float = 100.0):
    return _series([base] * length, START - timedelta(days=30))


def _catalog():
    return [
        {"id": 1, "code": "A2", "name": "酸奶 950ml", "category": "酸奶", "channel": "hypermarket", "cost": 10.22},
        {"id": 2, "code": "A3", "name": "果粒酸奶", "category": "酸奶", "channel": "convenience", "cost": 4.1},
        {"id": 3, "code": "A4", "name": "无糖酸奶", "category": "酸奶", "channel": "groupbuy", "cost": 7.4},
        {"id": 4, "code": "A6", "name": "希腊酸奶", "category": "酸奶", "channel": "hypermarket", "cost": 5.9},
        {"id": 5, "code": "A1", "name": "酸奶杯", "category": "酸奶", "channel": "distributor", "cost": 12.2},
    ]


def test_controls_come_from_same_category_and_skip_same_sku():
    catalog = _catalog()
    sales_index = {item["code"]: _index() for item in catalog}
    matched = measure.match_controls(
        sku=catalog[0],
        category_skus=catalog,
        sales_index=sales_index,
        events_by_sku={},
        guard_lo=date(2026, 8, 18),
        guard_hi=date(2026, 9, 7),
        match_lo=date(2026, 8, 18),
        match_hi=date(2026, 8, 31),
    )
    assert len(matched) == 3
    assert all(item["category"] == "酸奶" for item in matched)
    assert "A2" not in [item["code"] for item in matched]


def test_controls_with_overlapping_promo_are_excluded():
    catalog = _catalog()
    sales_index = {item["code"]: _index() for item in catalog}
    events_by_sku = {"A3": [{"start_on": date(2026, 8, 20), "end_on": date(2026, 8, 25)}]}
    matched = measure.match_controls(
        sku=catalog[0],
        category_skus=catalog,
        sales_index=sales_index,
        events_by_sku=events_by_sku,
        guard_lo=date(2026, 8, 18),
        guard_hi=date(2026, 9, 7),
        match_lo=date(2026, 8, 18),
        match_hi=date(2026, 8, 31),
    )
    assert "A3" not in [item["code"] for item in matched]
    assert len(matched) == 3


def test_measure_event_end_to_end_lift():
    catalog = _catalog()
    sku = catalog[0]
    pre_start = date(2026, 8, 18)
    promo_start = date(2026, 9, 1)
    treat = {}
    for offset in range(14):
        treat[pre_start + timedelta(days=offset)] = {"qty": 180, "price": 12.8, "is_promo": False}
    for offset in range(7):
        treat[promo_start + timedelta(days=offset)] = {"qty": 212, "price": 11.65, "is_promo": True}
    sales_index = {"A2": treat}
    for item in catalog[1:]:
        sales_index[item["code"]] = _index()
    event = {
        "id": 1,
        "event_no": "PE-2601",
        "channel": "hypermarket",
        "base_price": 12.8,
        "promo_price": 11.65,
        "discount": 0.09,
        "start_on": promo_start,
        "end_on": promo_start + timedelta(days=6),
        "kind": "discount",
    }
    result = measure.measure_event(
        event=event,
        sku=sku,
        category_skus=catalog,
        sales_index=sales_index,
        events_by_sku={"A2": [event]},
    )
    assert result["baseline_qty"] == 180.0
    assert result["actual_qty"] == 212.0
    assert abs(result["lift_pct"] - (212 / 180 - 1)) < 1e-4
    assert result["roi"] >= 1.2
    assert result["control_skus"]["codes"]


def test_measure_event_without_controls_is_unknown():
    catalog = _catalog()[:1]
    sku = catalog[0]
    sales_index = {"A2": _series([100.0] * 40, START - timedelta(days=10))}
    event = {
        "id": 1,
        "event_no": "PE-2601",
        "channel": "hypermarket",
        "base_price": 12.8,
        "promo_price": 11.65,
        "discount": 0.09,
        "start_on": START + timedelta(days=10),
        "end_on": START + timedelta(days=16),
        "kind": "discount",
    }
    result = measure.measure_event(
        event=event, sku=sku, category_skus=catalog, sales_index=sales_index, events_by_sku={}
    )
    assert result["state"] == "unknown"
    assert result["lift_pct"] is None
    assert "对照" in result["note"]
