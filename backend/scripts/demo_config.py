"""演示数据配置（纯数据 + 纯生成函数，不依赖数据库，可单独导入用于单测/调参）。

口径
----
- 数据窗口固定为 90 天，截止日 `ANCHOR_DATE`（写死，保证 seed 幂等、两次逐字一致）。
- 48 个 SKU = 6 个品类 × 8 个单品，每个 SKU 固定一个渠道（商超 / 便利店 / 社区团购 / 二批商），
  因此日销量事实表 = 48 × 90 = 4320 行。
- 日销量由「基础销量 × 星期系数 × 品类自然增长 × 价格弹性 × 噪声」生成：
  qty = base_volume * weekday * trend * (price / list_price) ** elasticity * noise
  促销日价格取促销价，非促销日价格在牌价 ±4% 内小幅波动（渠道调价），
  所以弹性既能被促销价差识别，也有连续的价格变异。
- 20 场活动的促销价 / 成本刻意做成不同毛利结构：A2 弹性 −1.8、毛利率厚 → ROI 1.24；
  B1 毛利率薄 → 增量很大但 ROI 0.70（「折扣越做越亏」的典型）。
"""
from __future__ import annotations

import math
from datetime import date, timedelta

DEMO_PASSWORD = "Demo@2026"

DEMO_USERS = [
    ("admin@pricelift.io", "林可 · 平台管理员", "admin"),
    ("analyst@pricelift.io", "周棠 · 价格分析师", "analyst"),
    ("viewer@pricelift.io", "陈默 · 销售只读", "viewer"),
]

ORG = "牧原乳品 · 区域销售部"

ANCHOR_DATE = date(2026, 11, 12)
WINDOW_DAYS = 90
START_DATE = ANCHOR_DATE - timedelta(days=WINDOW_DAYS - 1)

WEEKDAY_FACTOR = [1.10, 1.02, 0.94, 0.96, 1.04, 1.18, 1.22]  # 周一 .. 周日

# 自然增长（品类日增速）：90 天累计约 +2% ~ +5%，DID 会用它构造对照组反事实
CATEGORY_TREND = {
    "酸奶": 0.00040,
    "纯奶": 0.00028,
    "低温奶": 0.00056,
    "乳饮料": 0.00034,
    "奶酪": 0.00052,
    "稀奶油": 0.00024,
}

CHANNEL_BY_INDEX = ["hypermarket", "convenience", "groupbuy", "distributor"] * 2

# code, name, category, spec, list_price, elasticity, wobble(±比例), 备注
_CATALOG_SPEC = [
    ("A1", "酸奶 100g×8杯", "酸奶", "100g×8", 15.90, -1.45, 0.040),
    ("A2", "酸奶 950ml", "酸奶", "950ml", 12.80, -1.7737, 0.042),
    ("A3", "果粒酸奶 200g", "酸奶", "200g", 5.60, -1.62, 0.038),
    ("A4", "无糖酸奶 380g", "酸奶", "380g", 9.90, -1.28, 0.035),
    ("A5", "儿童酸奶 100g×6", "酸奶", "100g×6", 13.50, -2.05, 0.045),
    ("A6", "希腊式酸奶 135g", "酸奶", "135g", 7.80, -1.72, 0.040),
    ("A7", "酸奶 1.8kg 餐饮装", "酸奶", "1.8kg", 26.80, -1.15, 0.030),
    ("A8", "常温酸奶 200g×12", "酸奶", "200g×12", 39.90, -1.36, 0.032),
    ("B1", "纯奶 250ml×12", "纯奶", "250ml×12", 15.80, -1.74, 0.040),
    ("B2", "纯奶 250ml", "纯奶", "250ml", 2.90, -1.52, 0.036),
    ("B3", "纯奶 1L", "纯奶", "1L", 11.50, -1.62, 0.038),
    ("B4", "高钙奶 250ml×12", "纯奶", "250ml×12", 19.80, -1.32, 0.034),
    ("B5", "纯奶 200ml×24", "纯奶", "200ml×24", 33.50, -1.20, 0.030),
    ("B6", "有机纯奶 250ml", "纯奶", "250ml", 6.90, -1.95, 0.046),
    ("B7", "纯奶 1L×6", "纯奶", "1L×6", 62.00, -1.10, 0.028),
    ("B8", "早餐奶 250ml×12", "纯奶", "250ml×12", 17.90, -1.44, 0.036),
    ("C1", "低温鲜奶 950ml", "低温奶", "950ml", 16.90, -1.68, 0.040),
    ("C2", "低温鲜奶 450ml", "低温奶", "450ml", 9.50, -1.85, 0.044),
    ("C3", "巴氏鲜奶 200ml", "低温奶", "200ml", 4.20, -1.55, 0.038),
    ("C4", "低温酸奶 180g", "低温奶", "180g", 6.50, -1.78, 0.042),
    ("C5", "低温鲜奶 1.5L", "低温奶", "1.5L", 22.80, -1.40, 0.034),
    ("C6", "儿童鲜奶 200ml×6", "低温奶", "200ml×6", 14.50, -1.62, 0.040),
    ("C7", "低温酸奶 400g", "低温奶", "400g", 11.90, -1.48, 0.036),
    ("C8", "鲜奶 200ml×12", "低温奶", "200ml×12", 27.50, -1.30, 0.032),
    ("D1", "乳酸菌饮品 340ml", "乳饮料", "340ml", 6.80, -1.58, 0.040),
    ("D2", "乳饮料 250ml×6", "乳饮料", "250ml×6", 12.90, -1.35, 0.036),
    ("D3", "含乳饮料 500ml", "乳饮料", "500ml", 5.50, -1.72, 0.042),
    ("D4", "乳酸菌 100ml×5", "乳饮料", "100ml×5", 8.90, -1.92, 0.046),
    ("D5", "果味乳饮 450ml", "乳饮料", "450ml", 7.20, -1.46, 0.038),
    ("D6", "乳饮料 1L", "乳饮料", "1L", 9.80, -1.65, 0.040),
    ("D7", "儿童乳饮 200ml×4", "乳饮料", "200ml×4", 10.50, -1.22, 0.030),
    ("D8", "乳酸菌 330ml×4", "乳饮料", "330ml×4", 15.50, -1.50, 0.036),
    ("E1", "奶酪棒 500g", "奶酪", "500g", 39.90, -0.95, 0.026),
    ("E2", "马苏里拉 200g", "奶酪", "200g", 18.50, -1.12, 0.030),
    ("E3", "芝士片 168g", "奶酪", "168g", 14.80, -1.26, 0.032),
    ("E4", "儿童奶酪棒 90g×5", "奶酪", "90g×5", 32.00, -0.88, 0.024),
    ("E5", "奶油奶酪 240g", "奶酪", "240g", 21.50, -1.05, 0.028),
    ("E6", "奶酪碎 200g", "奶酪", "200g", 16.90, -1.18, 0.030),
    ("E7", "手撕奶酪 160g", "奶酪", "160g", 19.80, -0.92, 0.026),
    ("E8", "奶酪棒 1kg", "奶酪", "1kg", 68.00, -0.80, 0.022),
    ("F1", "淡奶油 250ml", "稀奶油", "250ml", 17.50, -1.08, 0.028),
    ("F2", "黄油 200g", "稀奶油", "200g", 24.80, -1.15, 0.030),
    ("F3", "淡奶油 1L", "稀奶油", "1L", 45.00, -0.98, 0.026),
    ("F4", "动物黄油 227g", "稀奶油", "227g", 32.50, -1.02, 0.028),
    ("F5", "稀奶油 500ml", "稀奶油", "500ml", 29.90, -1.20, 0.030),
    ("F6", "发酵黄油 200g", "稀奶油", "200g", 29.50, -0.94, 0.026),
    ("F7", "淡奶油 200ml×3", "稀奶油", "200ml×3", 26.00, -1.05, 0.000),
    ("F8", "无盐黄油 454g", "稀奶油", "454g", 58.00, -0.90, 0.000),
]

# 成本率（成本 / 牌价）：A2 与 B1 按验收口径写死，其余按品类给区间
_COST_RATIO = {
    "A2": 0.7985,  # 12.80 牌价 / 11.65 促销价 / 10.22 成本 → ROI 1.24
    "B1": 0.7956,  # 15.80 牌价 / 13.90 促销价 / 12.57 成本 → ROI 0.70
}
_DEFAULT_COST_RATIO = {
    "酸奶": 0.735,
    "纯奶": 0.775,
    "低温奶": 0.755,
    "乳饮料": 0.720,
    "奶酪": 0.700,
    "稀奶油": 0.712,
}


def _hash_unit(*parts: object) -> float:
    """稳定的字符串哈希 → [0,1)：不用 random，保证跨进程可复现。"""
    text = "|".join(str(part) for part in parts)
    h = 2166136261
    for ch in text:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return (h % 100000) / 100000.0


def _base_volume(list_price: float, code: str) -> int:
    raw = 1500.0 / (list_price**0.92)
    jitter = 0.78 + 0.44 * _hash_unit("vol", code)
    return max(18, int(round(raw * jitter)))


def build_catalog() -> list[dict]:
    catalog: list[dict] = []
    counters: dict[str, int] = {}
    for index, (code, name, category, spec, list_price, elasticity, wobble) in enumerate(_CATALOG_SPEC):
        position = counters.get(category, 0)
        counters[category] = position + 1
        ratio = _COST_RATIO.get(code) or _DEFAULT_COST_RATIO[category]
        ratio += (0.004 * (position - 3)) if code not in _COST_RATIO else 0.0
        cost = round(list_price * ratio, 2)
        catalog.append(
            {
                "code": code,
                "name": name,
                "category": category,
                "spec": spec,
                "channel": CHANNEL_BY_INDEX[position],
                "cost": cost,
                "list_price": list_price,
                "elasticity": elasticity,
                "base_volume": _base_volume(list_price, code),
                "wobble": wobble,
            }
        )
    return catalog


# 20 场活动：event_no, sku_code, start_offset(自窗口首日), days, kind, discount_pct, note
_EVENT_SPEC = [
    ("PE-2601", "A2", 18, 7, "discount", 1.24, "酸奶 950ml 直接降价：弹性高、毛利厚，增量能覆盖让利"),
    ("PE-2602", "B1", 24, 7, "discount", 0.70, "纯奶整箱让利：走量不走利，ROI 0.70 标记亏损"),
    ("PE-2603", "C2", 26, 6, "second_half", 0.62, "低温鲜奶第二件半价，毛利被打穿"),
    ("PE-2604", "A5", 30, 7, "discount", 2.31, "儿童酸奶开学季，浅折扣高弹性"),
    ("PE-2605", "D1", 34, 5, "member_day", 2.05, "乳酸菌会员日"),
    ("PE-2606", "E3", 36, 7, "threshold", 1.72, "芝士片满 59 减 8"),
    ("PE-2607", "B3", 38, 7, "discount", 1.06, "纯奶 1L 大促，勉强打平"),
    ("PE-2608", "C4", 40, 6, "discount", 1.42, "低温酸奶周末档"),
    ("PE-2609", "F2", 42, 7, "threshold", 1.18, "黄油烘焙季满减"),
    ("PE-2610", "A7", 44, 7, "discount", 2.60, "餐饮装酸奶渠道补贴"),
    ("PE-2611", "D4", 46, 5, "second_half", 1.65, "乳酸菌第二件半价"),
    ("PE-2612", "E5", 48, 7, "member_day", 1.05, "奶油奶酪会员专享，接近打平"),
    ("PE-2613", "B6", 50, 7, "discount", 0.31, "有机奶深度折扣：折扣越做越亏"),
    ("PE-2614", "C7", 52, 6, "threshold", 1.38, "低温酸奶满减"),
    ("PE-2615", "D6", 56, 7, "discount", 2.20, "乳饮料 1L 堆头"),
    ("PE-2616", "E8", 58, 7, "discount", 1.55, "奶酪棒家庭装"),
    ("PE-2617", "F5", 62, 7, "member_day", 2.75, "稀奶油会员日"),
    ("PE-2618", "A8", 64, 7, "threshold", 1.12, "常温酸奶整箱满减"),
    ("PE-2619", "C8", 68, 6, "discount", 1.85, "鲜奶整箱特价"),
    ("PE-2620", "D8", 72, 6, "second_half", 1.96, "乳酸菌礼盒第二件半价"),
]


def build_events(catalog: list[dict]) -> list[dict]:
    """促销价由「目标 ROI」反推：discount = (1 - cost/price) / (1 + target_roi)。

    ROI（边际口径）= 单件促销毛利 / 单件让利 = (1 - d - r) / d，其中 r = cost / 牌价。
    反解得到 d = (1 - r) / (1 + target_roi)，这样每场活动的折扣深度与其毛利结构自洽：
    毛利厚的品类敢做浅折扣，薄毛利品类做深折扣就会亏。
    """
    by_code = {item["code"]: item for item in catalog}
    events: list[dict] = []
    for event_no, code, offset, days, kind, target_roi, note in _EVENT_SPEC:
        sku = by_code[code]
        base_price = sku["list_price"]
        ratio = sku["cost"] / base_price
        discount_pct = (1.0 - ratio) / (1.0 + target_roi)
        promo_price = round(base_price * (1.0 - discount_pct), 2)
        if promo_price >= base_price:
            promo_price = round(base_price - 0.1, 2)
        start_on = START_DATE + timedelta(days=offset)
        events.append(
            {
                "event_no": event_no,
                "sku_code": code,
                "channel": sku["channel"],
                "base_price": base_price,
                "promo_price": promo_price,
                "discount": round(1.0 - promo_price / base_price, 4),
                "start_on": start_on,
                "end_on": start_on + timedelta(days=days - 1),
                "kind": kind,
                "note": note,
                "seed_key": f"seed-event-{event_no.lower()}",
            }
        )
    return events


def weekday_factor(day: date) -> float:
    return WEEKDAY_FACTOR[day.weekday()]


def build_sales(catalog: list[dict], events: list[dict]) -> list[dict]:
    """生成 48 × 90 = 4320 行日销量（确定性，无随机源）。"""
    promo_map: dict[tuple[str, date], dict] = {}
    for event in events:
        span = (event["end_on"] - event["start_on"]).days
        for offset in range(span + 1):
            promo_map[(event["sku_code"], event["start_on"] + timedelta(days=offset))] = event

    rows: list[dict] = []
    for sku in catalog:
        base = sku["list_price"]
        for offset in range(WINDOW_DAYS):
            day = START_DATE + timedelta(days=offset)
            event = promo_map.get((sku["code"], day))
            if event is not None:
                price = event["promo_price"]
                is_promo = True
            else:
                wobble = sku["wobble"] * 1.15 * (2.0 * _hash_unit("px", sku["code"], day.isoformat()) - 1.0)
                price = round(base * (1.0 + wobble), 2)
                is_promo = False
            trend = 1.0 + CATEGORY_TREND[sku["category"]] * offset
            noise = 1.0 + 0.012 * (2.0 * _hash_unit("qz", sku["code"], day.isoformat()) - 1.0)
            qty = (
                sku["base_volume"]
                * weekday_factor(day)
                * trend
                * math.pow(price / base, sku["elasticity"])
                * noise
            )
            units = max(1, int(round(qty)))
            rows.append(
                {
                    "sku_code": sku["code"],
                    "channel": sku["channel"],
                    "sold_on": day,
                    "qty": units,
                    "price": price,
                    "revenue": round(units * price, 2),
                    "is_promo": is_promo,
                    "event_no": event["event_no"] if event else None,
                }
            )
    return rows


def dataset() -> tuple[list[dict], list[dict], list[dict]]:
    catalog = build_catalog()
    events = build_events(catalog)
    sales = build_sales(catalog, events)
    return catalog, events, sales
