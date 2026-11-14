"""活动增量测算的纯装配层：活动 → 处理组 / 对照组日序列 → 弹性 + DID。

只接受普通 dict 与 date，不 import SQLAlchemy，可直接单测（tests/test_measure.py）。
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from src.constants.enums import roi_band
from src.constants.limits import CONTROL_COUNT, MIN_POST_DAYS, PRE_WINDOW_DAYS
from src.services import did, elasticity


def measure_event(
    *,
    event: dict,
    sku: dict,
    category_skus: Sequence[dict],
    sales_index: dict[str, dict[date, dict]],
    events_by_sku: dict[str, list[dict]],
    pre_days: int = PRE_WINDOW_DAYS,
) -> dict:
    """对一场活动算出复盘条目。"""
    start: date = event["start_on"]
    end: date = event["end_on"]
    window_lo = start - timedelta(days=pre_days)
    post_days = (end - start).days + 1

    treat_series = sales_index.get(sku["code"], {})
    treat_pre = series_values(treat_series, window_lo, start - timedelta(days=1))
    treat_post = series_values(treat_series, start, end)

    controls = match_controls(
        sku=sku,
        category_skus=category_skus,
        sales_index=sales_index,
        events_by_sku=events_by_sku,
        guard_lo=window_lo,
        guard_hi=end,
        match_lo=window_lo,
        match_hi=start - timedelta(days=1),
    )

    if controls:
        control_pre = aggregate(controls, sales_index, window_lo, start - timedelta(days=1))
        control_post = aggregate(controls, sales_index, start, end)
    else:
        control_pre = []
        control_post = []

    elas_rows = [
        {"price": item["price"], "qty": item["qty"], "is_promo": item["is_promo"], "weekday": day.weekday()}
        for day, item in sorted(treat_series.items())
    ]
    elas = elasticity.estimate_elasticity(elas_rows)

    if post_days < MIN_POST_DAYS or not controls or not control_pre or not control_post:
        result = did.compute_did(
            treat_pre=treat_pre,
            treat_post=treat_post,
            control_pre=control_pre or treat_pre,
            control_post=control_post or treat_post,
            base_price=event["base_price"],
            promo_price=event["promo_price"],
            unit_cost=sku["cost"],
            post_days=post_days,
        )
        result["state"] = "unknown"
        result["reason"] = "窗口不足或无可用对照 SKU"
        result["note"] = "窗口不足或无可用对照 SKU，未给出增量结论"
        result["lift_pct"] = None
    else:
        result = did.compute_did(
            treat_pre=treat_pre,
            treat_post=treat_post,
            control_pre=control_pre,
            control_post=control_post,
            base_price=event["base_price"],
            promo_price=event["promo_price"],
            unit_cost=sku["cost"],
            post_days=post_days,
        )

    result.update(
        {
            "event_id": event["id"],
            "sku_id": sku["id"],
            "event_no": event["event_no"],
            "sku_code": sku["code"],
            "sku_name": sku["name"],
            "category": sku["category"],
            "channel": event.get("channel") or sku["channel"],
            "kind": event["kind"],
            "start_on": start,
            "end_on": end,
            "base_price": event["base_price"],
            "promo_price": event["promo_price"],
            "discount": event.get("discount") or round(1 - event["promo_price"] / event["base_price"], 4),
            "cost": sku["cost"],
            "elasticity": elas["beta"],
            "elasticity_state": elas["state"],
            "elasticity_p_value": elas["p_value"],
            "elasticity_t": elas["t_value"],
            "elasticity_r2": elas["r2"],
            "elasticity_note": elasticity.elasticity_note(elas),
            "sample_days": elas["n"],
            "control_skus": {
                "codes": [item["code"] for item in controls],
                "names": [item["name"] for item in controls],
            },
        }
    )
    result["roi_band"] = roi_band(result.get("roi"))
    return result


def series_values(series: dict[date, dict], lo: date, hi: date) -> list[float]:
    days = (hi - lo).days
    if days < 0:
        return []
    values: list[float] = []
    for offset in range(days + 1):
        item = series.get(lo + timedelta(days=offset))
        if item is not None:
            values.append(float(item["qty"]))
    return values


def aggregate(
    controls: Sequence[dict],
    sales_index: dict[str, dict[date, dict]],
    lo: date,
    hi: date,
) -> list[float]:
    """对照组日销量 = 匹配到的同行 SKU 当日均值。"""
    days = (hi - lo).days
    if days < 0:
        return []
    series = [sales_index.get(item["code"], {}) for item in controls]
    values: list[float] = []
    for offset in range(days + 1):
        day = lo + timedelta(days=offset)
        samples = [float(entry[day]["qty"]) for entry in series if day in entry]
        if samples:
            values.append(sum(samples) / len(samples))
    return values


def match_controls(
    *,
    sku: dict,
    category_skus: Sequence[dict],
    sales_index: dict[str, dict[date, dict]],
    events_by_sku: dict[str, list[dict]],
    guard_lo: date,
    guard_hi: date,
    match_lo: date,
    match_hi: date,
) -> list[dict]:
    """同品类、窗口内无活动，按活动前日均销量规模取最接近的 3 个。"""
    target = series_values(sales_index.get(sku["code"], {}), match_lo, match_hi)
    target_avg = sum(target) / len(target) if target else 0.0
    scored: list[tuple[float, str, dict]] = []
    for candidate in category_skus:
        if candidate["code"] == sku["code"]:
            continue
        if has_overlap(events_by_sku.get(candidate["code"], []), guard_lo, guard_hi):
            continue
        pre = series_values(sales_index.get(candidate["code"], {}), match_lo, match_hi)
        if not pre:
            continue
        avg = sum(pre) / len(pre)
        scored.append((abs(avg - target_avg), candidate["code"], candidate))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in scored[:CONTROL_COUNT]]


def has_overlap(events: Sequence[dict], lo: date, hi: date) -> bool:
    for event in events:
        if event["end_on"] >= lo and event["start_on"] <= hi:
            return True
    return False
