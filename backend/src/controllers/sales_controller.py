"""销量曲线控制器。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.services import sales_service


def series(db: Session, sku_id: int, days: int) -> dict:
    return sales_service.series(db, sku_id, days)
