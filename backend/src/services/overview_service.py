"""总览：活动/复盘计数、平均弹性、亏损活动、90 天销量指数曲线、worker 心跳。"""
from __future__ import annotations

import time
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.constants.enums import (
    CHANNEL_LABELS,
    ISOLATION_REASON_LABELS,
    ISOLATION_REASON_ORDER,
    REPORT_STATUS_LABELS,
    ROI_BAND_LABELS,
    ROI_BAND_ORDER,
    RUN_STATUS_LABELS,
)
from src.models.lift_isolation import LiftIsolation
from src.models.lift_report import LiftReport
from src.models.lift_run import LiftRun
from src.models.price_event import PriceEvent
from src.models.sales_daily import SalesDaily
from src.models.sku import Sku
from src.utils.timeutil import iso_date, iso_utc


def worker_alive() -> bool:
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2)
        value = client.get(f"{settings.app_name}:worker:heartbeat")
        return bool(value) and (time.time() - float(value)) < 120
    except Exception:
        return False


def _merged_windows(events: list[tuple[date, date]]) -> list[dict]:
    """把重叠的促销窗口合并成带状阴影，供曲线图直接画。"""
    if not events:
        return []
    ordered = sorted(events)
    merged: list[list[date]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1] + timedelta(days=1):
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [{"start_on": iso_date(start), "end_on": iso_date(end), "days": (end - start).days + 1} for start, end in merged]


def overview(db: Session) -> dict:
    skus_total = db.scalar(select(func.count()).select_from(Sku)) or 0
    events_total = db.scalar(select(func.count()).select_from(PriceEvent)) or 0
    runs_total = db.scalar(select(func.count()).select_from(LiftRun)) or 0

    latest_run = db.scalar(select(LiftRun).order_by(LiftRun.id.desc()).limit(1))
    # 总览均值只取「可算活动」：复盘表里只有可算活动，隔离记录单独存放，
    # 因此 count(reports) = 可算数，count(isolations) = 隔离数，二者相加等于活动总数。
    latest_run_id = latest_run.id if latest_run else None
    if latest_run_id is not None:
        reports_total = db.scalar(
            select(func.count()).select_from(LiftReport).where(LiftReport.run_id == latest_run_id)
        ) or 0
        pending_total = db.scalar(
            select(func.count())
            .select_from(LiftReport)
            .where(LiftReport.run_id == latest_run_id, LiftReport.status == "pending")
        ) or 0
        avg_elasticity = db.scalar(
            select(func.avg(LiftReport.elasticity)).where(
                LiftReport.run_id == latest_run_id, LiftReport.elasticity.is_not(None)
            )
        )
        avg_roi = db.scalar(
            select(func.avg(LiftReport.roi)).where(LiftReport.run_id == latest_run_id, LiftReport.roi.is_not(None))
        )
        avg_lift = db.scalar(
            select(func.avg(LiftReport.lift_pct)).where(
                LiftReport.run_id == latest_run_id, LiftReport.lift_pct.is_not(None)
            )
        )
        band_rows = dict(
            db.execute(
                select(LiftReport.roi_band, func.count())
                .where(LiftReport.run_id == latest_run_id)
                .group_by(LiftReport.roi_band)
            ).all()
        )
        status_rows = dict(
            db.execute(
                select(LiftReport.status, func.count())
                .where(LiftReport.run_id == latest_run_id)
                .group_by(LiftReport.status)
            ).all()
        )
        loss_reports = db.scalars(
            select(LiftReport)
            .where(LiftReport.run_id == latest_run_id, LiftReport.roi_band == "loss")
            .order_by(LiftReport.roi.is_(None), LiftReport.roi)
            .limit(5)
        ).all()
        top_reports = db.scalars(
            select(LiftReport)
            .where(LiftReport.run_id == latest_run_id, LiftReport.lift_pct.is_not(None))
            .order_by(LiftReport.lift_pct.desc())
            .limit(3)
        ).all()
    else:
        avg_elasticity = avg_roi = avg_lift = None
        band_rows, status_rows = {}, {}
        loss_reports, top_reports = [], []
        reports_total = 0
        pending_total = 0

    isolation_rows: dict[str, int] = {}
    if latest_run_id is not None:
        isolation_rows = dict(
            db.execute(
                select(LiftIsolation.reason, func.count())
                .where(LiftIsolation.run_id == latest_run_id)
                .group_by(LiftIsolation.reason)
            ).all()
        )
    isolated_total = sum(isolation_rows.values())
    isolation_reasons = [
        {"key": key, "label": ISOLATION_REASON_LABELS.get(key, key), "count": isolation_rows.get(key, 0)}
        for key in ISOLATION_REASON_ORDER
    ]

    roi_bands = [
        {"key": key, "label": ROI_BAND_LABELS.get(key, key), "count": band_rows.get(key, 0)}
        for key in ROI_BAND_ORDER
    ]

    review = [
        {"key": key, "label": label, "count": status_rows.get(key, 0)}
        for key, label in REPORT_STATUS_LABELS.items()
    ]

    channel_rows = dict(
        db.execute(
            select(PriceEvent.channel, func.count()).group_by(PriceEvent.channel)
        ).all()
    )
    channels = [
        {"key": key, "label": label, "count": channel_rows.get(key, 0)}
        for key, label in CHANNEL_LABELS.items()
    ]

    skus = {item.id: item for item in db.scalars(select(Sku)).all()}
    events = {item.id: item for item in db.scalars(select(PriceEvent)).all()}

    hero = _hero(db)
    latest_events = latest_run.metrics.get("events") if latest_run else None
    return {
        "skus_total": skus_total,
        "events_total": events_total,
        "runs_total": runs_total,
        "reports_total": reports_total,
        "pending_total": pending_total,
        "loss_total": band_rows.get("loss", 0),
        # 对账口径（页面与导出共用）：活动总数 = 可算数 + 隔离数；原因计数之和 = 隔离数。
        "reconciliation": {
            "run_id": latest_run_id,
            "run_no": latest_run.run_no if latest_run else None,
            "events_total": latest_events,
            "calculable_count": reports_total,
            "isolated_count": isolated_total,
            "reason_total": sum(item["count"] for item in isolation_reasons),
            "balanced": (
                latest_events is not None
                and latest_events == reports_total + isolated_total
                and sum(item["count"] for item in isolation_reasons) == isolated_total
            ),
        },
        "isolation_reasons": isolation_reasons,
        "isolated_total": isolated_total,
        "avg_elasticity": round(avg_elasticity, 4) if avg_elasticity is not None else None,
        "avg_roi": round(avg_roi, 4) if avg_roi is not None else None,
        "avg_lift_pct": round(avg_lift, 4) if avg_lift is not None else None,
        "worker_alive": worker_alive(),
        "latest_run": {
            "id": latest_run.id,
            "run_no": latest_run.run_no,
            "status": latest_run.status,
            "status_label": RUN_STATUS_LABELS.get(latest_run.status, latest_run.status),
            "started_at": iso_utc(latest_run.started_at),
            "report_count": latest_run.report_count,
            "event_count": latest_run.event_count,
            "metrics": latest_run.metrics or {},
        }
        if latest_run
        else None,
        "roi_bands": roi_bands,
        "review": review,
        "channels": channels,
        "loss_events": [
            _brief(item, skus, events) for item in loss_reports
        ],
        "top_events": [_brief(item, skus, events) for item in top_reports],
        "hero": hero,
    }


def _brief(report: LiftReport, skus: dict, events: dict) -> dict:
    event = events.get(report.event_id)
    sku = skus.get(report.sku_id)
    return {
        "report_id": report.id,
        "event_no": event.event_no if event else None,
        "sku_name": sku.name if sku else None,
        "sku_code": sku.code if sku else None,
        "lift_pct": report.lift_pct,
        "roi": report.roi,
        "roi_band": report.roi_band,
        "roi_band_label": ROI_BAND_LABELS.get(report.roi_band, report.roi_band),
        "elasticity": report.elasticity,
    }


def _hero(db: Session) -> dict:
    rows = db.execute(
        select(SalesDaily.sold_on, func.sum(SalesDaily.qty), func.sum(SalesDaily.revenue))
        .group_by(SalesDaily.sold_on)
        .order_by(SalesDaily.sold_on)
    ).all()
    if not rows:
        return {"points": [], "windows": [], "days": 0}
    totals = [float(row[1] or 0) for row in rows]
    mean = sum(totals) / len(totals) if totals else 0.0
    points = [
        {
            "date": iso_date(row[0]),
            "qty": int(row[1] or 0),
            "revenue": round(float(row[2] or 0), 2),
            "index": round((float(row[1] or 0) / mean * 100), 2) if mean else 0.0,
        }
        for row in rows
    ]
    events = db.execute(select(PriceEvent.start_on, PriceEvent.end_on)).all()
    return {
        "points": points,
        "windows": _merged_windows([(start, end) for start, end in events]),
        "days": len(points),
        "mean_qty": round(mean, 1),
    }
