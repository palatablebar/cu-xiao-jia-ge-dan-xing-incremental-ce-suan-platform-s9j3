"""算法 B：DID（双重差分）增量测算 + ROI（纯函数）。

口径
----
处理组 = 活动 SKU；对照组 = 同品类、未在该窗口做活动的 SKU，按活动前销量规模匹配 3 个
（按活动前日均销量与处理组的绝对差排序取前 3）。

    Δtreat  = post_treat / pre_treat          （处理组后/前比）
    Δctrl   = post_ctrl  / pre_ctrl           （对照组后/前比，代表自然增长 + 季节性）
    baseline = pre_treat * Δctrl              （反事实日销量）
    actual   = post_treat                     （实际日销量）
    lift     = actual / baseline - 1          （DID 口径增量率）

平行趋势：活动前 14 天把处理组与对照组各自按自身均值归一，用最小二乘拟合日均斜率；
|slope_treat - slope_ctrl| < 0.1 视为通过，否则标记「平行趋势存疑」，结论仍给出但降级提示。

ROI（边际让利口径，本项目在 README 中固定）
    incremental_qty   = (actual - baseline) * post_days
    incremental_margin= incremental_qty * (promo_price - cost)
    promo_cost        = incremental_qty * (base_price - promo_price)
    roi               = incremental_margin / promo_cost

即「增量毛利 / 增量单元的让利额」= 单件促销毛利 / 单件让利率。
若按全量让利口径（让利额按实际销量算），ROI 会被 1+lift 稀释，本项目不用该口径。
"""
from __future__ import annotations

from collections.abc import Sequence

from src.constants.enums import roi_band
from src.constants.limits import PARALLEL_TREND_MAX_GAP


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def normalized_slope(values: Sequence[float]) -> float:
    """把序列按自身均值归一后，对日序号做最小二乘斜率（单位：倍数/天）。"""
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    if mean <= 0:
        return 0.0
    series = [value / mean for value in values]
    n = len(series)
    xs = list(range(n))
    mean_x = (n - 1) / 2.0
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator <= 0:
        return 0.0
    numerator = sum((xs[i] - mean_x) * (series[i] - 1.0) for i in range(n))
    return numerator / denominator


def parallel_trend_gap(treat_pre: Sequence[float], control_pre: Sequence[float]) -> float:
    """两条前窗曲线的归一斜率差（绝对值），<0.1 视为平行。"""
    return abs(normalized_slope(treat_pre) - normalized_slope(control_pre))


def compute_did(
    *,
    treat_pre: Sequence[float],
    treat_post: Sequence[float],
    control_pre: Sequence[float],
    control_post: Sequence[float],
    base_price: float,
    promo_price: float,
    unit_cost: float,
    post_days: int | None = None,
) -> dict:
    """返回 baseline/actual/lift/roi 等结构化结果；样本不足时 lift 为 None。"""
    days = post_days or len(treat_post)
    if not treat_pre or not treat_post or not control_pre or not control_post or days <= 0:
        return {
            "state": "unknown",
            "reason": "活动窗口内销量样本不足",
            "baseline_qty": 0.0,
            "actual_qty": 0.0,
            "incremental_qty": 0,
            "lift_pct": None,
            "roi": None,
            "roi_band": roi_band(None),
            "parallel_ok": False,
            "trend_gap": 0.0,
            "incremental_margin": 0.0,
            "promo_cost": 0.0,
            "unit_margin": round(promo_price - unit_cost, 4),
            "unit_discount": round(base_price - promo_price, 4),
            "note": "样本不足，未给出增量结论",
        }

    pre_treat = _mean(treat_pre)
    post_treat = _mean(treat_post)
    pre_ctrl = _mean(control_pre)
    post_ctrl = _mean(control_post)

    if pre_treat <= 0 or pre_ctrl <= 0:
        return {
            "state": "unknown",
            "reason": "活动前销量为 0，无法构造反事实",
            "baseline_qty": 0.0,
            "actual_qty": round(post_treat, 2),
            "incremental_qty": 0,
            "lift_pct": None,
            "roi": None,
            "roi_band": roi_band(None),
            "parallel_ok": False,
            "trend_gap": 0.0,
            "incremental_margin": 0.0,
            "promo_cost": 0.0,
            "unit_margin": round(promo_price - unit_cost, 4),
            "unit_discount": round(base_price - promo_price, 4),
            "note": "活动前销量为 0，无法构造反事实",
        }

    control_ratio = post_ctrl / pre_ctrl
    baseline = pre_treat * control_ratio
    actual = post_treat
    lift = (actual / baseline) - 1.0 if baseline > 0 else 0.0

    incremental_qty = int(round((actual - baseline) * days))
    unit_margin = round(promo_price - unit_cost, 4)
    unit_discount = round(base_price - promo_price, 4)
    incremental_margin = round(incremental_qty * unit_margin, 2)
    promo_cost = round(incremental_qty * unit_discount, 2)
    roi = None
    if incremental_qty > 0 and unit_discount > 0:
        roi = round(incremental_margin / promo_cost, 4)

    gap = parallel_trend_gap(treat_pre, control_pre)
    parallel_ok = gap < PARALLEL_TREND_MAX_GAP

    if incremental_qty <= 0:
        note = f"增量 {incremental_qty} 件：活动期没有跑赢自然增长，ROI 不计"
    elif parallel_ok:
        note = (
            f"基线 {baseline:.1f} → 实际 {actual:.1f} 件/日，增量 {incremental_qty} 件；"
            f"增量毛利 {incremental_margin:.0f} 元 / 增量让利 {promo_cost:.0f} 元"
        )
    else:
        note = (
            f"平行趋势存疑（前窗斜率差 {gap:.3f}），增量 {incremental_qty} 件仅供参考；"
            f"增量毛利 {incremental_margin:.0f} 元 / 增量让利 {promo_cost:.0f} 元"
        )

    return {
        "state": "ok",
        "reason": "" if parallel_ok else "平行趋势存疑",
        "baseline_qty": round(baseline, 2),
        "actual_qty": round(actual, 2),
        "incremental_qty": incremental_qty,
        "lift_pct": round(lift, 4),
        "roi": roi,
        "roi_band": roi_band(roi),
        "parallel_ok": parallel_ok,
        "trend_gap": round(gap, 4),
        "incremental_margin": incremental_margin,
        "promo_cost": promo_cost,
        "unit_margin": unit_margin,
        "unit_discount": unit_discount,
        "note": note,
    }
