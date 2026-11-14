"""测算编排：读写数据库，调用 services.measure 里的纯算法装配。

算法本体在 src/services/{measure,elasticity,did}.py，均为纯函数，可脱离数据库单测。
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import (
    ISOLATION_REASON_LABELS,
    ISOLATION_REASON_ORDER,
    RunStatus,
    TriggerKind,
    roi_band,
)
from src.constants.limits import PRE_WINDOW_DAYS
from src.models.lift_isolation import LiftIsolation
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
    metrics = run.metrics or {}
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
        "calculable_count": metrics.get("eligible", run.report_count),
        "isolated_count": metrics.get("isolated", 0),
        "isolation_reasons": metrics.get("isolation_reasons", {}),
        "metrics": metrics,
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
        isolated: list[dict] = []
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
            # 活动总数按「有 SKU 主数据的活动」统计，缺日 / 对照 / 价格问题一律走隔离，
            # 不再用「活动窗是否落在数据首尾之间」把活动从总数里静默丢掉。
            covered += 1
            result = measure.measure_event(
                event=event,
                sku=sku,
                category_skus=by_category.get(sku["category"], []),
                sales_index=sales_index,
                events_by_sku=events_by_sku,
                pre_days=run.pre_days,
            )
            if result["eligible"]:
                results.append(result)
            else:
                isolated.append(result)

        results.sort(key=lambda item: (item["start_on"], item["event_no"]))
        isolated.sort(key=lambda item: (item["start_on"], item["event_no"]))
        _upsert_reports(db, run, results)
        _upsert_isolations(db, run, isolated)
        _purge_stale(
            db,
            run,
            kept_reports={r["event_id"] for r in results},
            kept_isolations={r["event_id"] for r in isolated},
        )

        elasticities = [r["elasticity"] for r in results if r["elasticity"] is not None]
        lifts = [r["lift_pct"] for r in results if r["lift_pct"] is not None]
        rois = [r["roi"] for r in results if r["roi"] is not None]
        # 亏损口径与 roi_band 一致：ROI<1，以及「没有增量、ROI 不计」的可算活动。
        loss = sum(1 for r in results if roi_band(r.get("roi")) == "loss")
        reason_counts = {key: 0 for key in ISOLATION_REASON_ORDER}
        for row in isolated:
            reason = row.get("isolation_reason") or "not_calculable"
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        run.event_count = covered
        run.report_count = len(results)
        run.metrics = {
            "events": covered,
            "reports": len(results),
            "eligible": len(results),
            "isolated": len(isolated),
            "isolation_reasons": reason_counts,
            "isolation_reason_labels": {
                key: ISOLATION_REASON_LABELS.get(key, key) for key in ISOLATION_REASON_ORDER
            },
            "avg_elasticity": round(sum(elasticities) / len(elasticities), 4) if elasticities else None,
            "avg_lift_pct": round(sum(lifts) / len(lifts), 4) if lifts else None,
            "avg_roi": round(sum(rois) / len(rois), 4) if rois else None,
            "loss_events": loss,
            "unknown_elasticity": sum(1 for r in results if r["elasticity"] is None),
            "parallel_warn": sum(1 for r in results if not r["parallel_ok"]),
            "window_days": run.window_days,
        }
        reason_text = " / ".join(
            f"{ISOLATION_REASON_LABELS.get(key, key)} {count}" for key, count in reason_counts.items()
        )
        run.log_text = (
            f"窗口 {run.window_days} 天 / 前窗 {run.pre_days} 天；"
            f"活动 {covered} 场 = 可算 {len(results)} + 隔离 {len(isolated)}（{reason_text}）；"
            f"平均弹性 {run.metrics['avg_elasticity']}（仅可算活动），"
            f"平均增量 {run.metrics['avg_lift_pct']}，亏损活动 {loss} 场"
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
            "baseline_qty": float(item["baseline_qty"]),
            "actual_qty": float(item["actual_qty"]),
            "incremental_qty": int(item["incremental_qty"]),
            "lift_pct": float(item["lift_pct"]),
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


def _upsert_isolations(db: Session, run: LiftRun, isolated: Sequence[dict]) -> None:
    for item in isolated:
        row = db.scalar(
            select(LiftIsolation).where(LiftIsolation.run_id == run.id, LiftIsolation.event_id == item["event_id"])
        )
        payload = {
            "sku_id": item["sku_id"],
            "reason": item["isolation_reason"],
            "start_on": item["start_on"],
            "end_on": item["end_on"],
            "detail": item.get("isolation_detail") or {},
            "note": item.get("note") or "",
        }
        if row is None:
            db.add(LiftIsolation(run_id=run.id, event_id=item["event_id"], **payload))
        else:
            for field, value in payload.items():
                setattr(row, field, value)


def _purge_stale(
    db: Session,
    run: LiftRun,
    *,
    kept_reports: set[int],
    kept_isolations: set[int],
) -> None:
    """同一批次重跑时清掉旧记录：可算 ↔ 隔离迁移后，另一侧不能留残影。"""
    for row in db.scalars(select(LiftReport).where(LiftReport.run_id == run.id)).all():
        if row.event_id not in kept_reports:
            db.delete(row)
    for row in db.scalars(select(LiftIsolation).where(LiftIsolation.run_id == run.id)).all():
        if row.event_id not in kept_isolations:
            db.delete(row)
    db.flush()


def create_and_execute(
    db: Session,
    *,
    trigger: str = TriggerKind.MANUAL.value,
    operator_email: str,
    seed_key: str | None = None,
    pre_days: int | None = None,
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
        pre_days=int(pre_days) if pre_days else PRE_WINDOW_DAYS,
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
