"""隔离记录控制器。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.services import lift_isolation_service


def list_isolations(db: Session, **filters) -> dict:
    return lift_isolation_service.list_isolations(db, **filters)
