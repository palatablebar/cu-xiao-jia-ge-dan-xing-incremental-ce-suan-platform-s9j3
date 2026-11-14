"""活动可算性校验（纯函数）：先核对窗口完整性，再判定能否进入测算。

规则
----
1. **窗口完整性**：活动前窗 `[start - pre_days, start - 1]` 与活动窗 `[start, end]` 内的
   每一天都必须有销量行。**零销量（qty=0）是真实观测**，不算缺日；只有整行缺失才计为缺日。
2. **价格异常**：活动价本身必须满足 `0 < promo_price < base_price`；窗口内成交价必须为正；
   活动窗内每个日历日的成交价与活动促销价的相对偏差超过 `PRICE_ANOMALY_TOLERANCE` 视为价格异常。
3. **对照不足**：同品类可用对照 SKU 少于 `MIN_CONTROL_COUNT` 个（缺日的候选会被排除）。
4. **无法测算**：窗口过短、活动前销量为 0 等无法构造反事实的情况，同样保留原因。

返回 `{"calculable": bool, "reason": <IsolationReason|"">, "detail": {...}, "checks": [...]}`。
`reason` 只取主因（按 缺日 → 价格异常 → 对照不足 → 无法测算 的优先级），
`checks` 保留每一项检查的结论，供页面与导出的隔离明细追溯。
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, timedelta

from src.constants.enums import ISOLATION_REASON_LABELS, IsolationReason
from src.constants.limits import (
    MIN_CONTROL_COUNT,
    MIN_POST_DAYS,
    PRICE_ANOMALY_TOLERANCE,
)

Series = dict[date, dict]


def expected_days(lo: date, hi: date) -> list[date]:
    span = (hi - lo).days
    if span < 0:
        return []
    return [lo + timedelta(days=offset) for offset in range(span + 1)]


def missing_days(series: Series, lo: date, hi: date) -> list[date]:
    """窗口内整行缺失的日期（qty=0 的行存在，算已观测）。"""
    return [day for day in expected_days(lo, hi) if day not in series]


def _mean_qty(series: Series, lo: date, hi: date) -> float:
    """窗口均值为 0 判据：只用已观测日计算；缺日会让该判据在窗口完整性检查处先失败。"""
    days = expected_days(lo, hi)
    observed = [day for day in days if day in series]
    if not days or not observed:
        return 0.0
    return sum(float(series[day]["qty"]) for day in observed) / len(observed)


CHECK_LABELS: dict[str, str] = {
    "window_structure": "窗口结构",
    "baseline": "反事实可构造",
}


def _check(key: str, ok: bool, note: str) -> dict:
    label = CHECK_LABELS.get(key) or ISOLATION_REASON_LABELS.get(key, key)
    return {"key": key, "label": label, "ok": ok, "note": note}


def price_issues(event: dict, series: Series, lo: date, hi: date) -> list[str]:
    """窗口内的价格异常清单；空列表表示价格数据可用。"""
    issues: list[str] = []
    base_price = float(event.get("base_price") or 0.0)
    promo_price = float(event.get("promo_price") or 0.0)
    if base_price <= 0:
        issues.append(f"牌价 {base_price:g} 必须为正数")
    if promo_price <= 0:
        issues.append(f"促销价 {promo_price:g} 必须为正数")
    elif base_price > 0 and promo_price >= base_price:
        issues.append(f"促销价 {promo_price:g} 未低于牌价 {base_price:g}")

    start: date = event["start_on"]
    end: date = event["end_on"]
    for day in expected_days(lo, hi):
        item = series.get(day)
        if item is None:
            continue
        price = float(item.get("price") or 0.0)
        if price <= 0:
            issues.append(f"{day.isoformat()} 成交价 {price:g}，不是有效价格")
            continue
        # 活动窗内的每个日历日都应执行活动促销价；偏差过大说明价格数据异常。
        if start <= day <= end and promo_price > 0:
            gap = abs(price - promo_price) / promo_price
            if gap > PRICE_ANOMALY_TOLERANCE:
                issues.append(
                    f"{day.isoformat()} 活动日成交价 {price:.2f} 与活动价 {promo_price:.2f} 偏差 {gap:.1%}"
                )
    return issues


def assess(
    *,
    event: dict,
    treat_series: Series,
    control_series: dict[str, Series],
    excluded_control_codes: Sequence[str] = (),
    pre_days: int,
    post_days: int,
) -> dict:
    """判定一场活动是否可算；不可算时给出主因与完整明细。"""
    start: date = event["start_on"]
    end: date = event["end_on"]
    window_lo = start - timedelta(days=pre_days)

    checks: list[dict] = []

    # 1) 窗口结构
    structure_ok = end >= start and post_days >= MIN_POST_DAYS
    if not structure_ok:
        note = (
            f"活动窗 {post_days} 天，少于最少 {MIN_POST_DAYS} 天"
            if end >= start
            else "活动结束日早于开始日"
        )
    else:
        note = f"前窗 {pre_days} 天 / 活动窗 {post_days} 天"
    checks.append(_check("window_structure", structure_ok, note))

    # 2) 窗口完整性（处理组 + 已匹配对照组）
    treat_missing = missing_days(treat_series, window_lo, end)
    control_missing = {
        code: missing_days(series, window_lo, end) for code, series in control_series.items()
    }
    control_missing = {code: days for code, days in control_missing.items() if days}
    missing_total = len(treat_missing) + sum(len(days) for days in control_missing.values())
    if missing_total:
        parts = []
        if treat_missing:
            parts.append(f"处理组缺 {len(treat_missing)} 天（{_brief_days(treat_missing)}）")
        for code, days in control_missing.items():
            parts.append(f"对照 {code} 缺 {len(days)} 天（{_brief_days(days)}）")
        missing_note = "；".join(parts)
    else:
        missing_note = "窗口内每个日历日都有销量行（零销量按真实观测计入）"
    checks.append(_check(IsolationReason.MISSING_DAYS.value, not missing_total, missing_note))

    # 3) 价格异常
    issues = price_issues(event, treat_series, window_lo, end)
    price_note = "活动日成交价与活动价一致" if not issues else "；".join(issues[:5])
    if len(issues) > 5:
        price_note += f"；等共 {len(issues)} 项"
    checks.append(_check(IsolationReason.PRICE_ANOMALY.value, not issues, price_note))

    # 4) 对照充足性
    control_count = len(control_series)
    controls_ok = control_count >= MIN_CONTROL_COUNT
    control_note = f"可用对照 {control_count} 个（需要 {MIN_CONTROL_COUNT} 个）"
    if excluded_control_codes:
        control_note += f"；{len(excluded_control_codes)} 个候选因窗口缺日被排除（{_brief_codes(excluded_control_codes)}）"
    checks.append(_check(IsolationReason.INSUFFICIENT_CONTROLS.value, controls_ok, control_note))

    # 5) 反事实可构造性（前窗均值为 0 时无法做比值）
    treat_pre_mean = _mean_qty(treat_series, window_lo, start - timedelta(days=1))
    control_pre_mean = (
        sum(_mean_qty(series, window_lo, start - timedelta(days=1)) for series in control_series.values())
        / control_count
        if control_count
        else 0.0
    )
    baseline_ok = structure_ok and treat_pre_mean > 0 and control_pre_mean > 0
    if not structure_ok:
        baseline_note = "窗口结构不成立，未检查基线"
    elif treat_pre_mean <= 0:
        baseline_note = "活动前销量均值为 0（零销量已按真实观测计入），无法构造反事实"
    elif control_pre_mean <= 0:
        baseline_note = "对照组活动前销量均值为 0，无法构造反事实"
    else:
        baseline_note = f"处理组前窗日均 {treat_pre_mean:.1f} 件，对照组 {control_pre_mean:.1f} 件"
    checks.append(_check("baseline", baseline_ok, baseline_note))

    by_key = {item["key"]: item for item in checks}
    reason = ""
    # 主因优先级：窗口结构 → 缺日 → 价格异常 → 对照不足 → 基线不可构造。
    if not structure_ok:
        reason = IsolationReason.NOT_CALCULABLE.value
    elif missing_total:
        reason = IsolationReason.MISSING_DAYS.value
    elif issues:
        reason = IsolationReason.PRICE_ANOMALY.value
    elif not controls_ok:
        reason = IsolationReason.INSUFFICIENT_CONTROLS.value
    elif not baseline_ok:
        reason = IsolationReason.NOT_CALCULABLE.value

    detail = {
        "missing_days": {
            "treat": [day.isoformat() for day in treat_missing],
            "controls": {code: [day.isoformat() for day in days] for code, days in control_missing.items()},
            "total": missing_total,
        },
        "price_issues": issues,
        "control_count": control_count,
        "control_required": MIN_CONTROL_COUNT,
        "excluded_controls": list(excluded_control_codes),
        "pre_days": pre_days,
        "post_days": post_days,
        "treat_pre_mean": round(treat_pre_mean, 2),
        "control_pre_mean": round(control_pre_mean, 2),
        "checks": checks,
    }
    return {
        "calculable": not reason,
        "reason": reason,
        "reason_label": ISOLATION_REASON_LABELS.get(reason, ""),
        "detail": detail,
        "checks": checks,
        "note": _reason_note(reason, by_key),
    }


def _reason_note(reason: str, by_key: dict) -> str:
    if not reason:
        return ""
    prefix = {
        IsolationReason.MISSING_DAYS.value: "窗口缺日，不做补位测算",
        IsolationReason.PRICE_ANOMALY.value: "价格异常，不进入增量测算",
        IsolationReason.INSUFFICIENT_CONTROLS.value: "对照不足，不做 DID 测算",
        IsolationReason.NOT_CALCULABLE.value: "数据无法支撑测算",
    }.get(reason, "已隔离")
    # 无法测算可能由窗口结构或反事实不可构造触发，取实际失败的那一项说明。
    check = by_key.get(reason) or by_key.get("window_structure") or by_key.get("baseline") or {}
    note = check.get("note") or ""
    return f"{prefix}：{note}" if note else prefix


def _brief_days(days: Iterable[date], limit: int = 4) -> str:
    ordered = sorted(days)
    shown = "、".join(day.isoformat() for day in ordered[:limit])
    return shown + (f" 等 {len(ordered)} 天" if len(ordered) > limit else "")


def _brief_codes(codes: Iterable[str], limit: int = 4) -> str:
    ordered = list(codes)
    shown = " / ".join(ordered[:limit])
    return shown + (" 等" if len(ordered) > limit else "")
