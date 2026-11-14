"""导出控制器：CSV 响应 + 审计。"""
from __future__ import annotations

from fastapi import Request, Response
from sqlalchemy.orm import Session

from src.services import audit_service, export_service
from src.utils.csv_export import csv_response_headers


def reports_csv(db: Session, run_id: int | None, principal: dict, request: Request) -> Response:
    content, count = export_service.reports_csv(db, run_id)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="export.reports",
        entity="lift_report",
        entity_id=run_id,
        detail={"rows": count, "bytes": len(content)},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers=csv_response_headers("lift-reports.csv"),
    )


def runs_csv(db: Session, principal: dict, request: Request) -> Response:
    content, count = export_service.runs_csv(db)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="export.runs",
        entity="lift_run",
        entity_id=None,
        detail={"rows": count, "bytes": len(content)},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers=csv_response_headers("lift-runs.csv"),
    )
