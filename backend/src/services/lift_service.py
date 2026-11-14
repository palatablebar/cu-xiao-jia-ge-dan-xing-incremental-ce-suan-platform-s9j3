"""测算编排：读写数据库，调用 services.measure 里的纯算法装配。

算法本体在 src/services/{measure,elasticity,did}.py，均为纯函数，可脱离数据库单测。
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import RunStatus, TriggerKind, roi_band
from src.constants.limits import PRE_WINDOW_DAYS
from src.models.lift_report import LiftReport
from src.models.lift_run import LiftRun
from src.models.price_event import PriceEvent
from src.models.sales_daily import SalesDaily
from src.models.sku import Sku
from src.services import audit_service, measure
from src.utils.errors import AppError
from src.utils.timeutil import iso_utc, local_now, utcnow


# ------------------------------------------------------------------ 数据库部分
def serialize(run: LiftRun) -> dict:
    return {
        "id": run.id,
        "run_no": run.run_no,
        "trigger": run.trigger,
        "status": run.status,
        "operator_email": run.operator_email,
        "window_days": run.window_days,
        "pre_days": run.pre_days,
        "post_days": run.post_days,
        "event_count": run.event_count,
        "report_count": run.report_count,
        "metrics": run.metrics or {},
        "log_text": run.log_text,
        "started_at": iso_utc(run.started_at),
        "finished_at": iso_utc(run.finished_at),
    }


def next_run_no(db: Session) -> str:
    prefix = f"LR{local_now():%Y%m%d}"
    count = db.scalar(select(func.count()).select_from(LiftRun).where(LiftRun.run_no.like(f"{prefix}%"))) or 0
    return f"{prefix}-{count + 1:04d}"


def _load_index(db: Session) -> tuple[dict[str, dict], dict[str, dict], dict[str, list[dict]], dict[str, list[dict]]]:
    skus = db.scalars(select(Sku).order_by(Sku.id)).all()
    events = db.scalars(select(PriceEvent).order_by(PriceEvent.start_on, PriceEvent.id)).all()
    sales = db.scalars(select(SalesDaily).order_by(SalesDaily.sku_id, SalesDaily.sold_on)).all()

    sku_by_id = {
        item.id: {
            "id": item.id,
            "code": item.code,
            "name": item.name,
            "category": item.category,
            "channel": item.channel,
            "cost": item.cost,
            "list_price": item.list_price,
        }
        for item in skus
    }
    code_by_id = {item.id: item.code for item in skus}
    event_dicts: list[dict] = [
        {
            "id": item.id,
            "event_no": item.event_no,
            "sku_id": item.sku_id,
            "channel": item.channel,
            "base_price": item.base_price,
            "promo_price": item.promo_price,
            "discount": item.discount,
            "start_on": item.start_on,
            "end_on": item.end_on,
            "kind": item.kind,
        }
        for item in events
    ]
    sales_index: dict[str, dict[date, dict]] = {}
    for item in sales:
        code = code_by_id.get(item.sku_id)
        if code is None:
            continue
        sales_index.setdefault(code, {})[item.sold_on] = {
            "qty": item.qty,
            "price": item.price,
            "is_promo": item.is_promo,
        }
    events_by_sku: dict[str, list[dict]] = {}
    for entry in event_dicts:
        events_by_sku.setdefault(code_by_id.get(entry["sku_id"], ""), []).append(entry)
    by_category: dict[str, list[dict]] = {}
    for item in sku_by_id.values():
        by_category.setdefault(item["category"], []).append(item)
    return sku_by_id, {"events": event_dicts}, events_by_sku, by_category


def execute_run(db: Session, run: LiftRun) -> LiftRun:
    run.status = RunStatus.RUNNING.value
    try:
        sku_by_id, _, events_by_sku, by_category = _load_index(db)
        sales_index = _sales_index(db)
        events = db.scalars(select(PriceEvent).order_by(PriceEvent.start_on, PriceEvent.id)).all()
        covered = 0
        results: list[dict] = []
        for item in events:
            sku = sku_by_id.get(item.sku_id)
            if sku is None:
                continue
            event = {
                "id": item.id,
                "event_no": item.event_no,
                "channel": item.channel,
                "base_price": item.base_price,
                "promo_price": item.promo_price,
                "discount": item.discount,
                "start_on": item.start_on,
                "end_on": item.end_on,
                "kind": item.kind,
            }
            series = sales_index.get(sku["code"], {})
            if not series:
                continue
            first, last = min(series), max(series)
            if event["start_on"] - timedelta(days=PRE_WINDOW_DAYS) < first or event["end_on"] > last:
                continue
            result = measure.measure_event(
                event=event,
                sku=sku,
                category_skus=by_category.get(sku["category"], []),
                sales_index=sales_index,
                events_by_sku=events_by_sku,
                pre_days=run.pre_days,
            )
            results.append(result)
            covered += 1

        results.sort(key=lambda item: (item["start_on"], item["event_no"]))
        _upsert_reports(db, run, results)
        elasticities = [r["elasticity"] for r in results if r["elasticity"] is not None]
        lifts = [r["lift_pct"] for r in results if r["lift_pct"] is not None]
        rois = [r["roi"] for r in results if r["roi"] is not None]
        loss = sum(1 for r in results if (r["roi"] is not None and r["roi"] < 1.0))
        run.event_count = covered
        run.report_count = len(results)
        run.metrics = {
            "events": covered,
            "reports": len(results),
            "avg_elasticity": round(sum(elasticities) / len(elasticities), 4) if elasticities else None,
            "avg_lift_pct": round(sum(lifts) / len(lifts), 4) if lifts else None,
            "avg_roi": round(sum(rois) / len(rois), 4) if rois else None,
            "loss_events": loss,
            "unknown_elasticity": sum(1 for r in results if r["elasticity"] is None),
            "parallel_warn": sum(1 for r in results if not r["parallel_ok"]),
            "window_days": run.window_days,
        }
        run.log_text = (
            f"窗口 {run.window_days} 天 / 前窗 {run.pre_days} 天 / 活动窗 {run.post_days} 天；"
            f"活动 {covered} 场 → 复盘 {len(results)} 条；"
            f"平均弹性 {run.metrics['avg_elasticity']}，平均增量 {run.metrics['avg_lift_pct']}，"
            f"亏损活动 {loss} 场"
        )
        run.status = RunStatus.SUCCESS.value if results else RunStatus.PARTIAL.value
    except Exception as exc:  # noqa: BLE001 - 运行失败要留痕
        run.status = RunStatus.FAILED.value
        run.log_text = f"测算失败：{exc}"
        run.metrics = {"error": str(exc)[:300]}
    run.finished_at = utcnow()
    db.flush()
    return run


def _sales_index(db: Session) -> dict[str, dict[date, dict]]:
    rows = db.execute(
        select(SalesDaily.sold_on, SalesDaily.qty, SalesDaily.price, SalesDaily.is_promo, Sku.code).join(
            Sku, Sku.id == SalesDaily.sku_id
        )
    ).all()
    index: dict[str, dict[date, dict]] = {}
    for sold_on, qty, price, is_promo, code in rows:
        index.setdefault(code, {})[sold_on] = {"qty": qty, "price": price, "is_promo": is_promo}
    return index


_REPORT_FIELDS = (
    "baseline_qty",
    "actual_qty",
    "incremental_qty",
    "lift_pct",
    "elasticity",
    "p_value",
    "t_value",
    "r2",
    "roi",
    "roi_band",
    "parallel_ok",
    "trend_gap",
    "control_skus",
    "sample_days",
    "note",
)


def _upsert_reports(db: Session, run: LiftRun, results: Sequence[dict]) -> None:
    for item in results:
        row = db.scalar(
            select(LiftReport).where(LiftReport.run_id == run.id, LiftReport.event_id == item["event_id"])
        )
        payload = {
            "baseline_qty": float(item.get("baseline_qty") or 0.0),
            "actual_qty": float(item.get("actual_qty") or 0.0),
            "incremental_qty": int(item.get("incremental_qty") or 0),
            "lift_pct": float(item.get("lift_pct") or 0.0),
            "elasticity": item.get("elasticity"),
            "p_value": item.get("elasticity_p_value"),
            "t_value": item.get("elasticity_t"),
            "r2": item.get("elasticity_r2"),
            "roi": item.get("roi"),
            "roi_band": item.get("roi_band") or roi_band(item.get("roi")),
            "parallel_ok": bool(item.get("parallel_ok")),
            "trend_gap": float(item.get("trend_gap") or 0.0),
            "control_skus": item.get("control_skus") or {},
            "sample_days": int(item.get("sample_days") or 0),
            "note": item.get("note") or "",
        }
        if row is None:
            db.add(LiftReport(run_id=run.id, event_id=item["event_id"], sku_id=item["sku_id"], **payload))
        else:
            for field, value in payload.items():
                setattr(row, field, value)


def create_and_execute(
    db: Session,
    *,
    trigger: str = TriggerKind.MANUAL.value,
    operator_email: str,
    seed_key: str | None = None,
) -> LiftRun:
    if seed_key:
        existing = db.scalar(select(LiftRun).where(LiftRun.seed_key == seed_key))
        if existing is not None:
            return existing
    run = LiftRun(
        run_no=next_run_no(db),
        trigger=trigger,
        status=RunStatus.RUNNING.value,
        operator_email=operator_email,
        seed_key=seed_key,
    )
    db.add(run)
    db.flush()
    return execute_run(db, run)


def list_runs(db: Session, status: str | None, limit: int, offset: int) -> dict:
    stmt = select(LiftRun)
    count_stmt = select(func.count()).select_from(LiftRun)
    if status:
        stmt = stmt.where(LiftRun.status == status)
        count_stmt = count_stmt.where(LiftRun.status == status)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(LiftRun.id.desc()).limit(limit).offset(offset)).all()
    return {"items": [serialize(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def get_run(db: Session, run_id: int) -> LiftRun:
    run = db.get(LiftRun, run_id)
    if run is None:
        raise AppError("NOT_FOUND", 404, {"entity": "lift_run", "id": run_id})
    return run


def record_review_audit(db: Session, report: LiftReport, principal: dict, ip: str | None) -> None:
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="lift.review",
        entity="lift_report",
        entity_id=report.id,
        detail={"status": report.status, "roi": report.roi},
        ip=ip,
    )
