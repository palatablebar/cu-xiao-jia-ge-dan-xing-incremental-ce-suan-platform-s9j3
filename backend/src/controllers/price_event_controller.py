"""价格活动控制器。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, price_event_service


def list_events(db: Session, **filters) -> dict:
    return price_event_service.list_events(db, **filters)


def get_event(db: Session, event_id: int) -> dict:
    event = price_event_service.get_event(db, event_id)
    return price_event_service.serialize(event)


def create_event(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    event = price_event_service.create_event(db, payload)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="event.create",
        entity="price_event",
        entity_id=event.id,
        detail={"event_no": event.event_no, "discount": event.discount},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return price_event_service.serialize(event)


def update_event(db: Session, event_id: int, payload: dict, principal: dict, request: Request) -> dict:
    event = price_event_service.get_event(db, event_id)
    price_event_service.update_event(db, event, payload)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="event.update",
        entity="price_event",
        entity_id=event.id,
        detail={"fields": list(payload.keys()), "discount": event.discount},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return price_event_service.serialize(event)
