"""SKU 服务：主数据 CRUD、弹性快照、活动与销量摘要。"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import CHANNEL_LABELS
from src.models.price_event import PriceEvent
from src.models.sales_daily import SalesDaily
from src.models.sku import Sku
from src.services import elasticity
from src.utils.errors import AppError, not_found
from src.utils.timeutil import iso_date, iso_utc

ORG = "牧原乳品 · 区域销售部"


def serialize(sku: Sku, *, event_count: int | None = None, elasticity_info: dict | None = None) -> dict:
    data = {
        "id": sku.id,
        "code": sku.code,
        "name": sku.name,
        "category": sku.category,
        "spec": sku.spec,
        "channel": sku.channel,
        "channel_label": CHANNEL_LABELS.get(sku.channel, sku.channel),
        "cost": round(sku.cost, 2),
        "list_price": round(sku.list_price, 2),
        "margin": round(sku.list_price - sku.cost, 2),
        "margin_rate": round((sku.list_price - sku.cost) / sku.list_price, 4) if sku.list_price else 0.0,
        "enabled": sku.enabled,
        "created_at": iso_utc(sku.created_at),
    }
    if event_count is not None:
        data["event_count"] = event_count
    if elasticity_info is not None:
        data["elasticity"] = elasticity_info["beta"]
        data["elasticity_state"] = elasticity_info["state"]
        data["elasticity_reason"] = elasticity_info["reason"]
        data["elasticity_p_value"] = elasticity_info["p_value"]
        data["elasticity_r2"] = elasticity_info["r2"]
        data["elasticity_note"] = elasticity.elasticity_note(elasticity_info)
    return data


def list_skus(
    db: Session,
    *,
    q: str | None = None,
    category: str | None = None,
    channel: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    stmt = select(Sku)
    count_stmt = select(func.count()).select_from(Sku)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Sku.name.ilike(like) | Sku.code.ilike(like))
        count_stmt = count_stmt.where(Sku.name.ilike(like) | Sku.code.ilike(like))
    if category:
        stmt = stmt.where(Sku.category == category)
        count_stmt = count_stmt.where(Sku.category == category)
    if channel:
        stmt = stmt.where(Sku.channel == channel)
        count_stmt = count_stmt.where(Sku.channel == channel)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(Sku.code).limit(limit).offset(offset)).all()
    counts = dict(
        db.execute(select(PriceEvent.sku_id, func.count()).group_by(PriceEvent.sku_id)).all()
    )
    return {
        "items": [serialize(row, event_count=counts.get(row.id, 0)) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_sku(db: Session, sku_id: int) -> Sku:
    sku = db.get(Sku, sku_id)
    if sku is None:
        raise not_found("sku", sku_id)
    return sku


def elasticity_for_sku(db: Session, sku: Sku) -> dict:
    rows = db.execute(
        select(SalesDaily.sold_on, SalesDaily.price, SalesDaily.qty, SalesDaily.is_promo)
        .where(SalesDaily.sku_id == sku.id)
        .order_by(SalesDaily.sold_on)
    ).all()
    return elasticity.estimate_elasticity(
        [
            {"price": price, "qty": qty, "is_promo": is_promo, "weekday": sold_on.weekday()}
            for sold_on, price, qty, is_promo in rows
        ]
    )


def detail(db: Session, sku_id: int) -> dict:
    sku = get_sku(db, sku_id)
    events = db.scalars(
        select(PriceEvent).where(PriceEvent.sku_id == sku.id).order_by(PriceEvent.start_on.desc())
    ).all()
    agg = db.execute(
        select(
            func.min(SalesDaily.sold_on),
            func.max(SalesDaily.sold_on),
            func.sum(SalesDaily.qty),
            func.count(),
        ).where(SalesDaily.sku_id == sku.id)
    ).one()
    promo_agg = db.execute(
        select(func.sum(SalesDaily.qty), func.count())
        .where(SalesDaily.sku_id == sku.id, SalesDaily.is_promo.is_(True))
    ).one()
    data = serialize(sku, event_count=len(events), elasticity_info=elasticity_for_sku(db, sku))
    data["events"] = [
        {
            "id": item.id,
            "event_no": item.event_no,
            "channel": item.channel,
            "base_price": round(item.base_price, 2),
            "promo_price": round(item.promo_price, 2),
            "discount": round(item.discount, 4),
            "start_on": iso_date(item.start_on),
            "end_on": iso_date(item.end_on),
            "kind": item.kind,
            "note": item.note,
        }
        for item in events
    ]
    data["sales"] = {
        "first_day": iso_date(agg[0]) if agg[0] else None,
        "last_day": iso_date(agg[1]) if agg[1] else None,
        "days": int(agg[3] or 0),
        "total_qty": int(agg[2] or 0),
        "promo_qty": int(promo_agg[0] or 0),
        "promo_days": int(promo_agg[1] or 0),
    }
    return data


def create_sku(db: Session, payload: dict) -> Sku:
    exists = db.scalar(select(Sku).where(Sku.code == payload["code"]))
    if exists is not None:
        raise AppError("CONFLICT", 409, {"code": payload["code"]})
    sku = Sku(
        code=payload["code"],
        name=payload["name"],
        category=payload["category"],
        spec=payload.get("spec") or "",
        channel=payload.get("channel") or "hypermarket",
        cost=float(payload.get("cost") or 0.0),
        list_price=float(payload.get("list_price") or 0.0),
        enabled=payload.get("enabled", True),
    )
    db.add(sku)
    db.flush()
    return sku


def update_sku(db: Session, sku: Sku, payload: dict) -> Sku:
    for field in ("name", "category", "spec", "channel", "cost", "list_price", "enabled"):
        if field in payload and payload[field] is not None:
            setattr(sku, field, payload[field])
    db.flush()
    return sku


def categories(db: Session) -> list[str]:
    return [row for row in db.scalars(select(Sku.category).distinct().order_by(Sku.category)).all()]


def window_bounds(db: Session) -> tuple[date | None, date | None]:
    row = db.execute(select(func.min(SalesDaily.sold_on), func.max(SalesDaily.sold_on))).one()
    return row[0], row[1]
