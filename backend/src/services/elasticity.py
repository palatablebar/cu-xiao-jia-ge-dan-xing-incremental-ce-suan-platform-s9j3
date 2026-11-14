"""算法 A：log-log 价格弹性 OLS（纯函数，无数据库、无第三方数值库）。

模型
    ln(qty_t) = b0 + b1 * ln(price_t) + Σ(γ_w * weekday_w) + b2 * promo_t + ε_t

- b1 就是价格弹性（对数-对数模型下即弹性系数）；
- 只保留 6 个星期哑变量（周一为基准），避免与截距共线；
- 正规方程 (X'X)β = X'y 用自写高斯消元（部分选主元）求解，并求 (X'X)⁻¹ 得到标准误；
- t 值 = β / se(β)，双侧 p 值用 t 分布（不完全 Beta 函数），R² = 1 - RSS/TSS。

边界（BRIEF 要求「样本 <30 或价格无变化 → unknown」）：
- 有效样本 < 30 → state=unknown, reason="样本不足（n<30）"
- ln(price) 标准差 < 1e-6 → state=unknown, reason="价格无变化"
- 正规方程奇异（如价格与促销标记完全共线）→ state=unknown, reason="设计矩阵奇异"
"""
from __future__ import annotations

import math
from collections.abc import Sequence

from src.constants.limits import MIN_ELASTICITY_SAMPLES, MIN_PRICE_SPREAD

Row = dict


# ---------------------------------------------------------------- 线性代数工具
def solve_linear(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    """高斯消元（部分选主元）解 A x = b；奇异返回 None。"""
    size = len(matrix)
    aug = [list(matrix[i]) + [vector[i]] for i in range(size)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            return None
        aug[col], aug[pivot] = aug[pivot], aug[col]
        head = aug[col][col]
        for row in range(col + 1, size):
            factor = aug[row][col] / head
            if factor == 0.0:
                continue
            for k in range(col, size + 1):
                aug[row][k] -= factor * aug[col][k]
    result = [0.0] * size
    for row in range(size - 1, -1, -1):
        acc = aug[row][size] - sum(aug[row][k] * result[k] for k in range(row + 1, size))
        result[row] = acc / aug[row][row]
    return result


def invert(matrix: list[list[float]]) -> list[list[float]] | None:
    """逐列解 A x = e_i，得到 A⁻¹；奇异返回 None。"""
    size = len(matrix)
    columns: list[list[float]] = []
    for index in range(size):
        unit = [0.0] * size
        unit[index] = 1.0
        column = solve_linear(matrix, unit)
        if column is None:
            return None
        columns.append(column)
    return [[columns[c][r] for c in range(size)] for r in range(size)]


# ---------------------------------------------------------------- t 分布 p 值
def _betacf(a: float, b: float, x: float) -> float:
    """不完全 Beta 的连分式（Lentz 算法）。"""
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 200):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """正则化不完全 Beta I_x(a,b)。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_two_sided_p(t_value: float | None, dof: int) -> float | None:
    """双侧 t 检验 p 值；dof<=0 或 t 缺失返回 None。"""
    if t_value is None or dof <= 0:
        return None
    t = abs(t_value)
    return _betai(dof / 2.0, 0.5, dof / (dof + t * t))


# ---------------------------------------------------------------- 主函数
def _unknown(reason: str, n: int) -> dict:
    return {
        "state": "unknown",
        "reason": reason,
        "n": n,
        "beta": None,
        "intercept": None,
        "promo_coef": None,
        "std_error": None,
        "t_value": None,
        "p_value": None,
        "r2": None,
        "price_spread": 0.0,
    }


def estimate_elasticity(rows: Sequence[Row]) -> dict:
    """用 90 天日数据估计 price elasticity。

    rows: [{"price": float, "qty": float, "is_promo": bool, "weekday": int(0=周一)}]
    """
    usable: list[tuple[float, float, float, int]] = []
    for row in rows:
        try:
            price = float(row["price"])
            qty = float(row["qty"])
        except (KeyError, TypeError, ValueError):
            continue
        if price <= 0 or qty <= 0:
            continue
        ln_price = math.log(price)
        ln_qty = math.log(qty)
        weekday = int(row.get("weekday") or 0) % 7
        promo = 1.0 if row.get("is_promo") else 0.0
        usable.append((ln_qty, ln_price, promo, weekday))

    n = len(usable)
    if n < MIN_ELASTICITY_SAMPLES:
        return _unknown(f"样本不足（n={n} < {MIN_ELASTICITY_SAMPLES}）", n)

    prices = [item[1] for item in usable]
    mean_price = sum(prices) / n
    spread = math.sqrt(sum((p - mean_price) ** 2 for p in prices) / (n - 1))
    if spread < MIN_PRICE_SPREAD:
        return _unknown("价格无变化，弹性不可识别", n)

    # 设计矩阵：截距 + ln(price) + [promo] + 6 个星期哑变量（周一为基准）。
    # 若整段样本没有促销日，promo 列全为 0 会让 X'X 奇异，此时直接去掉该项。
    has_promo = any(item[2] > 0 for item in usable)
    promo_index = 2 if has_promo else None
    design: list[list[float]] = []
    target: list[float] = []
    for ln_qty, ln_price, promo, weekday in usable:
        dummies = [1.0 if weekday == w + 1 else 0.0 for w in range(6)]
        row = [1.0, ln_price]
        if has_promo:
            row.append(promo)
        row.extend(dummies)
        design.append(row)
        target.append(ln_qty)

    width = len(design[0])
    xtx = [[sum(design[i][a] * design[i][b] for i in range(n)) for b in range(width)] for a in range(width)]
    xty = [sum(design[i][a] * target[i] for i in range(n)) for a in range(width)]
    beta = solve_linear(xtx, xty)
    if beta is None:
        return _unknown("设计矩阵奇异（价格与活动标记完全共线）", n)

    residuals = [
        target[i] - sum(beta[a] * design[i][a] for a in range(width)) for i in range(n)
    ]
    rss = sum(r * r for r in residuals)
    mean_y = sum(target) / n
    tss = sum((v - mean_y) ** 2 for v in target)
    r2 = 1.0 - rss / tss if tss > 0 else 0.0
    dof = n - width
    inverse = invert(xtx) if dof > 0 else None
    std_error = None
    t_value = None
    p_value = None
    if inverse is not None:
        sigma2 = rss / dof
        variance = sigma2 * inverse[1][1]
        if variance > 0:
            std_error = math.sqrt(variance)
            if std_error > 1e-12:
                t_value = beta[1] / std_error
                p_value = t_two_sided_p(t_value, dof)

    return {
        "state": "ok",
        "reason": "",
        "n": n,
        "beta": round(beta[1], 4),
        "intercept": round(beta[0], 4),
        "promo_coef": round(beta[promo_index], 4) if promo_index is not None else None,
        "std_error": round(std_error, 4) if std_error is not None else None,
        "t_value": round(t_value, 4) if t_value is not None else None,
        "p_value": p_value,
        "r2": round(r2, 4),
        "price_spread": round(spread, 4),
        "dof": dof,
    }


def elasticity_note(result: dict) -> str:
    """把估计结果翻成一句可读结论（页面与 CSV 共用）。"""
    if result["state"] != "ok":
        return f"弹性不可估计：{result['reason']}"
    sign = "富有弹性" if abs(result["beta"]) >= 1 else "缺乏弹性"
    return f"弹性 {result['beta']:.2f}（{sign}），t={result['t_value']:.2f}，R²={result['r2']:.2f}"
