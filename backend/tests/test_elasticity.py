"""算法 A（log-log 弹性 OLS）单测：识别精度、边界、确定性。"""
from __future__ import annotations

import math
import random

from src.services import elasticity


def _synthetic(truth: float, *, days: int = 90, promo_days: tuple[int, ...] = (), seed: int = 11):
    rng = random.Random(seed)
    rows = []
    for index in range(days):
        weekday = index % 7
        if index in promo_days:
            price, is_promo = 11.7, True
        else:
            price, is_promo = 12.8 * (1 + 0.045 * (2 * rng.random() - 1)), False
        weekday_factor = [1.10, 1.02, 0.94, 0.96, 1.04, 1.18, 1.22][weekday]
        qty = 180 * weekday_factor * math.pow(price / 12.8, truth) * (1 + 0.01 * (2 * rng.random() - 1))
        rows.append({"price": price, "qty": qty, "is_promo": is_promo, "weekday": weekday})
    return rows


def test_recovers_known_elasticity():
    result = elasticity.estimate_elasticity(_synthetic(-1.8))
    assert result["state"] == "ok"
    assert abs(result["beta"] - (-1.8)) < 0.12
    assert result["r2"] > 0.8


def test_p_value_significant_for_strong_signal():
    result = elasticity.estimate_elasticity(_synthetic(-1.8))
    assert result["t_value"] is not None and result["t_value"] < 0
    assert result["p_value"] is not None and result["p_value"] < 0.05


def test_promo_days_do_not_break_estimate():
    result = elasticity.estimate_elasticity(_synthetic(-1.8, promo_days=tuple(range(30, 37))))
    assert result["state"] == "ok"
    assert abs(result["beta"] - (-1.8)) < 0.15


def test_unknown_when_sample_too_small():
    result = elasticity.estimate_elasticity(_synthetic(-1.8, days=20))
    assert result["state"] == "unknown"
    assert "样本不足" in result["reason"]
    assert result["beta"] is None


def test_unknown_when_price_never_moves():
    rows = [{"price": 12.8, "qty": 100 + index, "is_promo": False, "weekday": index % 7} for index in range(60)]
    result = elasticity.estimate_elasticity(rows)
    assert result["state"] == "unknown"
    assert result["reason"] == "价格无变化，弹性不可识别"


def test_bad_rows_are_skipped():
    rows = _synthetic(-1.8, days=40) + [{"price": 0, "qty": 10}, {"price": 10, "qty": -3}]
    result = elasticity.estimate_elasticity(rows)
    assert result["n"] == 40


def test_elasticity_is_deterministic():
    first = elasticity.estimate_elasticity(_synthetic(-1.2, seed=5))
    second = elasticity.estimate_elasticity(_synthetic(-1.2, seed=5))
    assert first == second


def test_note_marks_inelastic_and_elastic():
    elastic = elasticity.estimate_elasticity(_synthetic(-1.8))
    assert "富有弹性" in elasticity.elasticity_note(elastic)
    weak = elasticity.estimate_elasticity(_synthetic(-0.4, seed=3))
    assert "缺乏弹性" in elasticity.elasticity_note(weak)
    unknown = elasticity.estimate_elasticity([])
    assert "不可估计" in elasticity.elasticity_note(unknown)


def test_t_p_value_helper_matches_reference():
    # 双侧 t 检验：t=2.0, dof=80 的 p 值约 0.0489
    assert abs(elasticity.t_two_sided_p(2.0, 80) - 0.0489) < 0.002
    assert elasticity.t_two_sided_p(None, 80) is None
    assert elasticity.t_two_sided_p(2.0, 0) is None
