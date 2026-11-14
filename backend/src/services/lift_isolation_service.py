"""隔离记录服务：列出不可算活动及其原因，供页面与导出对账。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import (
    CHANNEL_LABELS,
    EVENT_KIND_LABELS,
    ISOLATION_REASON_LABELS,
    ISOLATION_REASON_ORDER,
)
from src.models.lift_isolation import LiftIsolation
from src.models.lift_run import LiftRun
from src.models.price_event import PriceEvent
from src.models.sku import Sku
from src.utils.timeutil import iso_date, iso_utc


def serialize(row: LiftIsolation, run: LiftRun | None, event: PriceEvent | None, sku: Sku | None) -> dict:
    detail = row.detail or {}
    return {
        "id": row.id,
        "run_id": row.run_id,
        "run_no": run.run_no if run else None,
        "event_id": row.event_id,
        "event_no": event.event_no if event else None,
        "sku_id": row.sku_id,
        "sku_code": sku.code if sku else None,
        "sku_name": sku.name if sku else None,
        "category": sku.category if sku else None,
        "channel": event.channel if event else None,
        "channel_label": CHANNEL_LABELS.get(event.channel, event.channel) if event else None,
        "kind": event.kind if event else None,
        "kind_label": EVENT_KIND_LABELS.get(event.kind, event.kind) if event else None,
        "start_on": iso_date(row.start_on),
        "end_on": iso_date(row.end_on),
        "reason": row.reason,
        "reason_label": ISOLATION_REASON_LABELS.get(row.reason, row.reason),
        "detail": detail,
        "note": row.note,
        "created_at": iso_utc(row.created_at),
    }


def _context(db: Session) -> tuple[dict, dict, dict]:
    runs = {item.id: item for item in db.scalars(select(LiftRun)).all()}
    events = {item.id: item for item in db.scalars(select(PriceEvent)).all()}
    skus = {item.id: item for item in db.scalars(select(Sku)).all()}
    return runs, events, skus


def list_isolations(
    db: Session,
    *,
    run_id: int | None = None,
    reason: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    stmt = select(LiftIsolation)
    count_stmt = select(func.count()).select_from(LiftIsolation)
    if run_id:
        stmt = stmt.where(LiftIsolation.run_id == run_id)
        count_stmt = count_stmt.where(LiftIsolation.run_id == run_id)
    if reason:
        stmt = stmt.where(LiftIsolation.reason == reason)
        count_stmt = count_stmt.where(LiftIsolation.reason == reason)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(LiftIsolation.id.desc()).limit(limit).offset(offset)).all()
    runs, events, skus = _context(db)
    return {
        "items": [
            serialize(row, runs.get(row.run_id), events.get(row.event_id), skus.get(row.sku_id)) for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def reason_counts(db: Session, run_id: int | None = None) -> dict[str, int]:
    stmt = select(LiftIsolation.reason, func.count())
    if run_id:
        stmt = stmt.where(LiftIsolation.run_id == run_id)
    rows = dict(db.execute(stmt.group_by(LiftIsolation.reason)).all())
    return {key: rows.get(key, 0) for key in ISOLATION_REASON_ORDER}
