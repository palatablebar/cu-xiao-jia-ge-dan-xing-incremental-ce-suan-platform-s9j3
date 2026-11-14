"""测算与复盘控制器：跑批次、看复盘、提复盘结论。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, lift_report_service, lift_service


def create_run(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    run = lift_service.create_and_execute(
        db,
        trigger=payload.get("trigger") or "manual",
        operator_email=principal["email"],
    )
    if payload.get("pre_days") and payload["pre_days"] != run.pre_days:
        run.pre_days = int(payload["pre_days"])
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="lift.create",
        entity="lift_run",
        entity_id=run.id,
        detail={"run_no": run.run_no, "status": run.status, "reports": run.report_count},
        ip=request.client.host if request.client else None,
    )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="lift.complete",
        entity="lift_run",
        entity_id=run.id,
        detail={"status": run.status, "reports": run.report_count, "loss": (run.metrics or {}).get("loss_events")},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return lift_service.serialize(run)


def list_runs(db: Session, **filters) -> dict:
    return lift_service.list_runs(db, **filters)


def get_run(db: Session, run_id: int) -> dict:
    return lift_service.serialize(lift_service.get_run(db, run_id))


def list_reports(db: Session, **filters) -> dict:
    return lift_report_service.list_reports(db, **filters)


def get_report(db: Session, report_id: int) -> dict:
    return lift_report_service.detail(db, report_id)


def review_report(db: Session, report_id: int, payload: dict, principal: dict, request: Request) -> dict:
    report = lift_report_service.get_report(db, report_id)
    lift_report_service.review(
        db,
        report,
        status=payload["status"],
        note=payload.get("note"),
        reviewer=principal["email"],
    )
    lift_service.record_review_audit(db, report, principal, request.client.host if request.client else None)
    db.commit()
    return lift_report_service.detail(db, report.id)
