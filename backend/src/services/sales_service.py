"""销量曲线服务：单 SKU 90 天日序列 + 促销窗口 + 弹性快照。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants.enums import CHANNEL_LABELS, EVENT_KIND_LABELS
from src.models.price_event import PriceEvent
from src.models.sales_daily import SalesDaily
from src.services import elasticity, sku_service
from src.utils.timeutil import iso_date


def series(db: Session, sku_id: int, days: int = 90) -> dict:
    sku = sku_service.get_sku(db, sku_id)
    rows = db.execute(
        select(SalesDaily.sold_on, SalesDaily.qty, SalesDaily.price, SalesDaily.is_promo, SalesDaily.revenue)
        .where(SalesDaily.sku_id == sku.id)
        .order_by(SalesDaily.sold_on)
    ).all()
    if days and days < len(rows):
        rows = rows[-days:]

    points = [
        {
            "date": iso_date(sold_on),
            "qty": int(qty),
            "price": round(float(price), 2),
            "revenue": round(float(revenue), 2),
            "is_promo": bool(is_promo),
        }
        for sold_on, qty, price, is_promo, revenue in rows
    ]
    first = rows[0][0] if rows else None
    last = rows[-1][0] if rows else None

    windows: list[dict] = []
    if first and last:
        events = db.scalars(
            select(PriceEvent)
            .where(PriceEvent.sku_id == sku.id, PriceEvent.end_on >= first, PriceEvent.start_on <= last)
            .order_by(PriceEvent.start_on)
        ).all()
        windows = [
            {
                "id": item.id,
                "event_no": item.event_no,
                "start_on": iso_date(item.start_on),
                "end_on": iso_date(item.end_on),
                "kind": item.kind,
                "kind_label": EVENT_KIND_LABELS.get(item.kind, item.kind),
                "base_price": round(item.base_price, 2),
                "promo_price": round(item.promo_price, 2),
                "discount": round(item.discount, 4),
            }
            for item in events
        ]

    promo_qty = [point["qty"] for point in points if point["is_promo"]]
    base_qty = [point["qty"] for point in points if not point["is_promo"]]
    elas = elasticity.estimate_elasticity(
        [
            {"price": point["price"], "qty": point["qty"], "is_promo": point["is_promo"], "weekday": _weekday(point["date"])}
            for point in points
        ]
    )

    return {
        "sku": sku_service.serialize(sku),
        "channel_label": CHANNEL_LABELS.get(sku.channel, sku.channel),
        "points": points,
        "windows": windows,
        "elasticity": elas,
        "stats": {
            "days": len(points),
            "first_day": iso_date(first),
            "last_day": iso_date(last),
            "total_qty": sum(point["qty"] for point in points),
            "promo_days": len(promo_qty),
            "avg_promo_qty": round(sum(promo_qty) / len(promo_qty), 1) if promo_qty else 0,
            "avg_base_qty": round(sum(base_qty) / len(base_qty), 1) if base_qty else 0,
            "avg_price": round(sum(point["price"] for point in points) / len(points), 2) if points else 0,
        },
    }


def _weekday(text: str) -> int:
    from datetime import date

    return date.fromisoformat(text).weekday()
