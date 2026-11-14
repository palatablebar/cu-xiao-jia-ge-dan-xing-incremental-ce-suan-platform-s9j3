from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import sales_controller
from src.middlewares.rbac import READ_ROLES, require_roles

router = APIRouter(prefix="/sales", tags=["sales"])


@router.get("")
def sales_series(
    sku_id: int = Query(gt=0),
    days: int = Query(90, ge=7, le=180),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return sales_controller.series(db, sku_id, days)
