from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import lift_isolation_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.utils.pagination import page_params

router = APIRouter(prefix="/lift-isolations", tags=["lift-isolations"])


@router.get("")
def list_isolations(
    run_id: int | None = None,
    reason: str | None = None,
    limit: int = Query(20),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return lift_isolation_controller.list_isolations(
        db, run_id=run_id, reason=reason, limit=page.limit, offset=page.offset
    )
