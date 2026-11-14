"""活动增量测算的纯装配层：活动 → 窗口校验 → 处理组 / 对照组日序列 → 弹性 + DID。

只接受普通 dict 与 date，不 import SQLAlchemy，可直接单测（tests/test_measure.py）。

口径
----
先核对窗口完整性，再判定活动可算性（services/eligibility.py）：

- 缺日、对照不足、价格异常分别隔离，返回 `state="isolated"` 与主因 `reason`；
- **零销量是真实观测**，不算缺日；缺日不会被静默跳过，也不会拿处理组自己补位；
- 只有 `state="ok"` 的活动进入均值计算，隔离记录由调用方落库留档。
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from src.constants.enums import roi_band
from src.constants.limits import CONTROL_COUNT, PRE_WINDOW_DAYS
from src.services import did, eligibility, elasticity


def measure_event(
    *,
    event: dict,
    sku: dict,
    category_skus: Sequence[dict],
    sales_index: dict[str, dict[date, dict]],
    events_by_sku: dict[str, list[dict]],
    pre_days: int = PRE_WINDOW_DAYS,
) -> dict:
    """对一场活动算出复盘条目；不可算时返回 `state="isolated"` 与原因，不做补位测算。"""
    start: date = event["start_on"]
    end: date = event["end_on"]
    window_lo = start - timedelta(days=pre_days)
    post_days = (end - start).days + 1

    treat_series = sales_index.get(sku["code"], {})
    controls, excluded = match_controls(
        sku=sku,
        category_skus=category_skus,
        sales_index=sales_index,
        events_by_sku=events_by_sku,
        guard_lo=window_lo,
        guard_hi=end,
        match_lo=window_lo,
        match_hi=start - timedelta(days=1),
    )
    control_series = {item["code"]: sales_index.get(item["code"], {}) for item in controls}

    check = eligibility.assess(
        event=event,
        treat_series=treat_series,
        control_series=control_series,
        excluded_control_codes=excluded,
        pre_days=pre_days,
        post_days=post_days,
    )

    base = {
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
        "control_skus": {
            "codes": [item["code"] for item in controls],
            "names": [item["name"] for item in controls],
        },
        "pre_days": pre_days,
        "post_days": post_days,
        "eligible": check["calculable"],
        "isolation_reason": check["reason"],
        "isolation_reason_label": check["reason_label"],
        "isolation_detail": check["detail"],
        "isolation_checks": check["checks"],
    }

    if not check["calculable"]:
        return {
            **base,
            **_isolated_payload(check["note"]),
            "elasticity_note": "活动已隔离，未做弹性估计",
            "unit_margin": round(event["promo_price"] - sku["cost"], 4),
            "unit_discount": round(event["base_price"] - event["promo_price"], 4),
        }

    # 可算活动的窗口一定完整，series_values 不会遇到缺日。
    treat_pre = series_values(treat_series, window_lo, start - timedelta(days=1))
    treat_post = series_values(treat_series, start, end)
    control_pre = aggregate(controls, sales_index, window_lo, start - timedelta(days=1))
    control_post = aggregate(controls, sales_index, start, end)

    elas_rows = [
        {"price": item["price"], "qty": item["qty"], "is_promo": item["is_promo"], "weekday": day.weekday()}
        for day, item in sorted(treat_series.items())
    ]
    elas = elasticity.estimate_elasticity(elas_rows)

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
    if result["state"] != "ok":
        # 兜底：通过窗口校验却仍算不出增量的边界情况，同样隔离留档，不写成 0% 增量。
        return {
            **base,
            **_isolated_payload(result.get("note") or "增量无法计算"),
            "isolation_reason": "not_calculable",
            "isolation_reason_label": "无法测算",
            "isolation_detail": {
                **base["isolation_detail"],
                "did_reason": result.get("reason"),
            },
            "unit_margin": round(event["promo_price"] - sku["cost"], 4),
            "unit_discount": round(event["base_price"] - event["promo_price"], 4),
        }

    result.update(
        {
            **base,
            "elasticity": elas["beta"],
            "elasticity_state": elas["state"],
            "elasticity_p_value": elas["p_value"],
            "elasticity_t": elas["t_value"],
            "elasticity_r2": elas["r2"],
            "elasticity_note": elasticity.elasticity_note(elas),
            "sample_days": elas["n"],
        }
    )
    result["roi_band"] = roi_band(result.get("roi"))
    return result


def _isolated_payload(note: str) -> dict:
    """隔离活动的统一字段：一律 None，不写 0% 增量 / 亏损标签。"""
    return {
        "state": "isolated",
        "eligible": False,
        "reason": note,
        "note": note,
        "baseline_qty": None,
        "actual_qty": None,
        "incremental_qty": None,
        "lift_pct": None,
        "roi": None,
        "roi_band": "",
        "parallel_ok": False,
        "trend_gap": None,
        "incremental_margin": None,
        "promo_cost": None,
        "unit_margin": None,
        "unit_discount": None,
        "elasticity": None,
        "elasticity_state": "unknown",
        "elasticity_p_value": None,
        "elasticity_t": None,
        "elasticity_r2": None,
        "sample_days": 0,
    }


def series_values(series: dict[date, dict], lo: date, hi: date) -> list[float]:
    """按日历日取窗口内序列；缺日直接报错，绝不静默跳过或补位。"""
    values: list[float] = []
    for day in eligibility.expected_days(lo, hi):
        item = series.get(day)
        if item is None:
            raise ValueError(f"窗口缺日：{day.isoformat()}")
        values.append(float(item["qty"]))
    return values


def aggregate(
    controls: Sequence[dict],
    sales_index: dict[str, dict[date, dict]],
    lo: date,
    hi: date,
) -> list[float]:
    """对照组日销量 = 匹配到的同行 SKU 当日均值（缺日已在可算性校验中排除）。"""
    series = [sales_index.get(item["code"], {}) for item in controls]
    values: list[float] = []
    for day in eligibility.expected_days(lo, hi):
        samples = [float(entry[day]["qty"]) for entry in series if day in entry]
        if not samples:
            raise ValueError(f"对照组缺日：{day.isoformat()}")
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
) -> tuple[list[dict], list[str]]:
    """同品类、窗口内无活动，按活动前日均销量规模取最接近的 3 个。

    候选必须整窗完整（`guard_lo..guard_hi` 每个日历日都有销量行）；
    缺日的候选会被排除并记录在第二个返回值里，供隔离原因说明「为什么对照不足」。
    """
    treat_series = sales_index.get(sku["code"], {})
    target_values = [float(item["qty"]) for day, item in sorted(treat_series.items()) if match_lo <= day <= match_hi]
    target_avg = sum(target_values) / len(target_values) if target_values else 0.0
    scored: list[tuple[float, str, dict]] = []
    excluded: list[str] = []
    for candidate in category_skus:
        if candidate["code"] == sku["code"]:
            continue
        if has_overlap(events_by_sku.get(candidate["code"], []), guard_lo, guard_hi):
            continue
        candidate_series = sales_index.get(candidate["code"], {})
        if not window_complete(candidate_series, guard_lo, guard_hi):
            excluded.append(candidate["code"])
            continue
        pre = series_values(candidate_series, match_lo, match_hi)
        avg = sum(pre) / len(pre)
        scored.append((abs(avg - target_avg), candidate["code"], candidate))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in scored[:CONTROL_COUNT]], sorted(excluded)


def window_complete(series: dict[date, dict], lo: date, hi: date) -> bool:
    days = eligibility.expected_days(lo, hi)
    return bool(days) and all(day in series for day in days)


def has_overlap(events: Sequence[dict], lo: date, hi: date) -> bool:
    for event in events:
        if event["end_on"] >= lo and event["start_on"] <= hi:
            return True
    return False
