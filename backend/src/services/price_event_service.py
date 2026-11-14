"""价格活动服务：列表 / 详情 / 新建 / 改期。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import CHANNEL_LABELS, EVENT_KIND_LABELS
from src.models.price_event import PriceEvent
from src.models.sku import Sku
from src.services import sku_service
from src.utils.errors import AppError, not_found
from src.utils.timeutil import iso_date


def serialize(event: PriceEvent, sku: Sku | None = None) -> dict:
    return {
        "id": event.id,
        "event_no": event.event_no,
        "sku_id": event.sku_id,
        "sku_code": sku.code if sku else None,
        "sku_name": sku.name if sku else None,
        "category": sku.category if sku else None,
        "channel": event.channel,
        "channel_label": CHANNEL_LABELS.get(event.channel, event.channel),
        "base_price": round(event.base_price, 2),
        "promo_price": round(event.promo_price, 2),
        "discount": round(event.discount, 4),
        "start_on": iso_date(event.start_on),
        "end_on": iso_date(event.end_on),
        "days": (event.end_on - event.start_on).days + 1,
        "kind": event.kind,
        "kind_label": EVENT_KIND_LABELS.get(event.kind, event.kind),
        "note": event.note,
    }


def list_events(
    db: Session,
    *,
    q: str | None = None,
    sku_id: int | None = None,
    kind: str | None = None,
    channel: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    stmt = select(PriceEvent)
    count_stmt = select(func.count()).select_from(PriceEvent)
    if sku_id:
        stmt = stmt.where(PriceEvent.sku_id == sku_id)
        count_stmt = count_stmt.where(PriceEvent.sku_id == sku_id)
    if kind:
        stmt = stmt.where(PriceEvent.kind == kind)
        count_stmt = count_stmt.where(PriceEvent.kind == kind)
    if channel:
        stmt = stmt.where(PriceEvent.channel == channel)
        count_stmt = count_stmt.where(PriceEvent.channel == channel)
    if q:
        like = f"%{q.strip()}%"
        matching = select(Sku.id).where(Sku.name.ilike(like) | Sku.code.ilike(like))
        condition = PriceEvent.event_no.ilike(like) | PriceEvent.sku_id.in_(matching)
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(PriceEvent.start_on.desc(), PriceEvent.id).limit(limit).offset(offset)).all()
    skus = {item.id: item for item in db.scalars(select(Sku)).all()}
    return {
        "items": [serialize(row, skus.get(row.sku_id)) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_event(db: Session, event_id: int) -> PriceEvent:
    event = db.get(PriceEvent, event_id)
    if event is None:
        raise not_found("price_event", event_id)
    return event


def create_event(db: Session, payload: dict) -> PriceEvent:
    sku = sku_service.get_sku(db, payload["sku_id"])
    exists = db.scalar(select(PriceEvent).where(PriceEvent.event_no == payload["event_no"]))
    if exists is not None:
        raise AppError("CONFLICT", 409, {"event_no": payload["event_no"]})
    base_price = float(payload.get("base_price") or sku.list_price)
    promo_price = float(payload["promo_price"])
    if promo_price >= base_price or promo_price <= 0:
        raise AppError("VALIDATION", 422, {"promo_price": "促销价必须大于 0 且低于牌价"})
    event = PriceEvent(
        event_no=payload["event_no"],
        sku_id=sku.id,
        channel=payload.get("channel") or sku.channel,
        base_price=base_price,
        promo_price=promo_price,
        discount=round(1 - promo_price / base_price, 4),
        start_on=payload["start_on"],
        end_on=payload["end_on"],
        kind=payload.get("kind") or "discount",
        note=payload.get("note") or "",
    )
    if event.end_on < event.start_on:
        raise AppError("VALIDATION", 422, {"end_on": "结束日不能早于开始日"})
    db.add(event)
    db.flush()
    return event


def update_event(db: Session, event: PriceEvent, payload: dict) -> PriceEvent:
    for field in ("channel", "base_price", "promo_price", "start_on", "end_on", "kind", "note"):
        if field in payload and payload[field] is not None:
            setattr(event, field, payload[field])
    if event.promo_price >= event.base_price:
        raise AppError("VALIDATION", 422, {"promo_price": "促销价必须低于牌价"})
    event.discount = round(1 - event.promo_price / event.base_price, 4)
    db.flush()
    return event
