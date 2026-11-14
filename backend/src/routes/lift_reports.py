from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import REVIEW_ROLES
from src.controllers import lift_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.lift import ReviewIn
from src.utils.pagination import page_params

router = APIRouter(prefix="/lift-reports", tags=["lift-reports"])


@router.get("")
def list_reports(
    run_id: int | None = None,
    status: str | None = None,
    band: str | None = None,
    sku_id: int | None = None,
    q: str | None = None,
    limit: int = Query(20),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return lift_controller.list_reports(
        db, run_id=run_id, status=status, band=band, sku_id=sku_id, q=q, limit=page.limit, offset=page.offset
    )


@router.get("/{report_id}")
def get_report(
    report_id: int, db: Session = Depends(get_db), principal: dict = Depends(require_roles(*READ_ROLES))
) -> dict:
    return lift_controller.get_report(db, report_id)


@router.patch("/{report_id}/review")
def review(
    report_id: int,
    payload: ReviewIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*REVIEW_ROLES)),
) -> dict:
    return lift_controller.review_report(db, report_id, payload.model_dump(), principal, request)
