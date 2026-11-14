"""复盘条目服务：列表（多条件）/ 详情 / 复盘结论。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import (
    CHANNEL_LABELS,
    EVENT_KIND_LABELS,
    REPORT_STATUS_LABELS,
    ROI_BAND_LABELS,
    roi_band,
)
from src.models.lift_report import LiftReport
from src.models.lift_run import LiftRun
from src.models.price_event import PriceEvent
from src.models.sku import Sku
from src.utils.errors import AppError, not_found
from src.utils.timeutil import iso_date, iso_utc, utcnow


def serialize(report: LiftReport, run: LiftRun | None, event: PriceEvent | None, sku: Sku | None) -> dict:
    return {
        "id": report.id,
        "run_id": report.run_id,
        "run_no": run.run_no if run else None,
        "event_id": report.event_id,
        "event_no": event.event_no if event else None,
        "sku_id": report.sku_id,
        "sku_code": sku.code if sku else None,
        "sku_name": sku.name if sku else None,
        "category": sku.category if sku else None,
        "channel": event.channel if event else None,
        "channel_label": CHANNEL_LABELS.get(event.channel, event.channel) if event else None,
        "kind": event.kind if event else None,
        "kind_label": EVENT_KIND_LABELS.get(event.kind, event.kind) if event else None,
        "start_on": iso_date(event.start_on) if event else None,
        "end_on": iso_date(event.end_on) if event else None,
        "base_price": round(event.base_price, 2) if event else None,
        "promo_price": round(event.promo_price, 2) if event else None,
        "discount": round(event.discount, 4) if event else None,
        "baseline_qty": round(report.baseline_qty, 1),
        "actual_qty": round(report.actual_qty, 1),
        "incremental_qty": report.incremental_qty,
        "lift_pct": round(report.lift_pct, 4) if report.lift_pct is not None else None,
        "elasticity": report.elasticity,
        "p_value": report.p_value,
        "t_value": report.t_value,
        "r2": report.r2,
        "roi": report.roi,
        "roi_band": report.roi_band,
        "roi_band_label": ROI_BAND_LABELS.get(report.roi_band, report.roi_band),
        "parallel_ok": report.parallel_ok,
        "trend_gap": report.trend_gap,
        "control_skus": report.control_skus or {},
        "sample_days": report.sample_days,
        "status": report.status,
        "status_label": REPORT_STATUS_LABELS.get(report.status, report.status),
        "note": report.note,
        "reviewer": report.reviewer,
        "review_note": report.review_note,
        "created_at": iso_utc(report.created_at),
        "updated_at": iso_utc(report.updated_at),
    }


def _context(db: Session) -> tuple[dict, dict, dict]:
    runs = {item.id: item for item in db.scalars(select(LiftRun)).all()}
    events = {item.id: item for item in db.scalars(select(PriceEvent)).all()}
    skus = {item.id: item for item in db.scalars(select(Sku)).all()}
    return runs, events, skus


def list_reports(
    db: Session,
    *,
    run_id: int | None = None,
    status: str | None = None,
    band: str | None = None,
    sku_id: int | None = None,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    stmt = select(LiftReport)
    count_stmt = select(func.count()).select_from(LiftReport)
    if run_id:
        stmt = stmt.where(LiftReport.run_id == run_id)
        count_stmt = count_stmt.where(LiftReport.run_id == run_id)
    if status:
        stmt = stmt.where(LiftReport.status == status)
        count_stmt = count_stmt.where(LiftReport.status == status)
    if band:
        stmt = stmt.where(LiftReport.roi_band == band)
        count_stmt = count_stmt.where(LiftReport.roi_band == band)
    if sku_id:
        stmt = stmt.where(LiftReport.sku_id == sku_id)
        count_stmt = count_stmt.where(LiftReport.sku_id == sku_id)
    if q:
        like = f"%{q.strip()}%"
        matching_sku = select(Sku.id).where(Sku.name.ilike(like) | Sku.code.ilike(like))
        matching_event = select(PriceEvent.id).where(PriceEvent.event_no.ilike(like))
        condition = LiftReport.sku_id.in_(matching_sku) | LiftReport.event_id.in_(matching_event)
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(LiftReport.id.desc()).limit(limit).offset(offset)
    ).all()
    runs, events, skus = _context(db)
    return {
        "items": [serialize(row, runs.get(row.run_id), events.get(row.event_id), skus.get(row.sku_id)) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_report(db: Session, report_id: int) -> LiftReport:
    report = db.get(LiftReport, report_id)
    if report is None:
        raise not_found("lift_report", report_id)
    return report


def detail(db: Session, report_id: int) -> dict:
    report = get_report(db, report_id)
    runs, events, skus = _context(db)
    data = serialize(report, runs.get(report.run_id), events.get(report.event_id), skus.get(report.sku_id))
    event = events.get(report.event_id)
    if event is not None:
        data["event"] = {
            "event_no": event.event_no,
            "kind": event.kind,
            "kind_label": EVENT_KIND_LABELS.get(event.kind, event.kind),
            "start_on": iso_date(event.start_on),
            "end_on": iso_date(event.end_on),
            "base_price": round(event.base_price, 2),
            "promo_price": round(event.promo_price, 2),
            "discount": round(event.discount, 4),
            "note": event.note,
        }
    band = roi_band(report.roi)
    data["roi_band_label"] = ROI_BAND_LABELS.get(band, band)
    return data


def review(db: Session, report: LiftReport, *, status: str, note: str | None, reviewer: str) -> LiftReport:
    if status not in ("pending", "confirmed", "dismissed"):
        raise AppError("VALIDATION", 422, {"status": status})
    report.status = status
    report.review_note = note
    report.reviewer = reviewer
    report.updated_at = utcnow()
    db.flush()
    return report
