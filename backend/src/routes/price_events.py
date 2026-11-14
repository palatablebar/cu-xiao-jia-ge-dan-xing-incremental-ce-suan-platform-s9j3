from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import EVENT_WRITE_ROLES
from src.controllers import price_event_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.price_event import PriceEventIn, PriceEventPatch
from src.utils.pagination import page_params

router = APIRouter(prefix="/price-events", tags=["price-events"])


@router.get("")
def list_events(
    q: str | None = None,
    sku_id: int | None = None,
    kind: str | None = None,
    channel: str | None = None,
    limit: int = Query(20),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return price_event_controller.list_events(
        db, q=q, sku_id=sku_id, kind=kind, channel=channel, limit=page.limit, offset=page.offset
    )


@router.get("/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db), principal: dict = Depends(require_roles(*READ_ROLES))) -> dict:
    return price_event_controller.get_event(db, event_id)


@router.post("", status_code=201)
def create_event(
    payload: PriceEventIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EVENT_WRITE_ROLES)),
) -> dict:
    return price_event_controller.create_event(db, payload.model_dump(), principal, request)


@router.patch("/{event_id}")
def update_event(
    event_id: int,
    payload: PriceEventPatch,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*EVENT_WRITE_ROLES)),
) -> dict:
    return price_event_controller.update_event(db, event_id, payload.model_dump(exclude_unset=True), principal, request)
