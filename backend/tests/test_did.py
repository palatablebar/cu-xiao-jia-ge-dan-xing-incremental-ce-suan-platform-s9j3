"""算法 B（DID 增量 + ROI）单测：增量口径、平行趋势、边界与 ROI 分档。"""
from __future__ import annotations

from src.services import did


def _flat(values: list[float]) -> list[float]:
    return values


def test_known_lift_when_control_is_flat():
    result = did.compute_did(
        treat_pre=_flat([100.0] * 14),
        treat_post=_flat([118.0] * 7),
        control_pre=_flat([50.0] * 14),
        control_post=_flat([50.0] * 7),
        base_price=12.80,
        promo_price=11.65,
        unit_cost=10.22,
    )
    assert result["lift_pct"] == 0.18
    assert result["baseline_qty"] == 100.0
    assert result["actual_qty"] == 118.0
    assert result["incremental_qty"] == 126


def test_control_growth_is_removed():
    """对照组自然增长 10%，DID 应把这一段扣掉。"""
    result = did.compute_did(
        treat_pre=[100.0] * 14,
        treat_post=[118.0] * 7,
        control_pre=[50.0] * 14,
        control_post=[55.0] * 7,
        base_price=12.80,
        promo_price=11.65,
        unit_cost=10.22,
    )
    assert result["baseline_qty"] == 110.0
    assert abs(result["lift_pct"] - (118 / 110 - 1)) < 1e-4


def test_roi_is_margin_over_discount():
    result = did.compute_did(
        treat_pre=[100.0] * 14,
        treat_post=[118.0] * 7,
        control_pre=[50.0] * 14,
        control_post=[50.0] * 7,
        base_price=12.80,
        promo_price=11.65,
        unit_cost=10.22,
    )
    assert result["roi"] == round((11.65 - 10.22) / (12.80 - 11.65), 4)
    assert result["roi"] >= 1.2
    assert result["roi_band"] == "profit"


def test_loss_band_for_thin_margin():
    result = did.compute_did(
        treat_pre=[100.0] * 14,
        treat_post=[126.0] * 7,
        control_pre=[50.0] * 14,
        control_post=[50.0] * 7,
        base_price=15.80,
        promo_price=13.90,
        unit_cost=12.57,
    )
    assert result["roi"] < 1.0
    assert result["roi_band"] == "loss"


def test_parallel_trend_gap_detects_divergence():
    flat = [100.0] * 14
    rising = [100.0 * (1.3**index) for index in range(14)]
    assert did.parallel_trend_gap(flat, flat) == 0.0
    assert did.parallel_trend_gap(flat, rising) > 0.1
    assert did.normalized_slope(flat) == 0.0
    assert did.normalized_slope(rising) > 0.1


def test_parallel_trend_flag_on_report():
    rising = [50.0 * (1.2**index) for index in range(14)]
    result = did.compute_did(
        treat_pre=rising,
        treat_post=[400.0] * 7,
        control_pre=[100.0] * 14,
        control_post=[100.0] * 7,
        base_price=12.8,
        promo_price=11.65,
        unit_cost=10.22,
    )
    assert result["parallel_ok"] is False
    assert "平行趋势存疑" in result["note"]


def test_no_increment_means_no_roi():
    result = did.compute_did(
        treat_pre=[100.0] * 14,
        treat_post=[95.0] * 7,
        control_pre=[50.0] * 14,
        control_post=[50.0] * 7,
        base_price=12.8,
        promo_price=11.65,
        unit_cost=10.22,
    )
    assert result["incremental_qty"] < 0
    assert result["roi"] is None
    assert "没有跑赢自然增长" in result["note"]


def test_empty_windows_are_unknown():
    result = did.compute_did(
        treat_pre=[],
        treat_post=[],
        control_pre=[],
        control_post=[],
        base_price=12.8,
        promo_price=11.65,
        unit_cost=10.22,
    )
    assert result["state"] == "unknown"
    assert result["lift_pct"] is None
    assert result["roi_band"] == "loss"
