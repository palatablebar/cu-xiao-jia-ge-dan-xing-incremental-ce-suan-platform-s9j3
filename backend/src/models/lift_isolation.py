"""隔离记录：活动不可算时保留原因（缺日 / 对照不足 / 价格异常 / 无法测算）。

一场活动在一个批次里只会有一条隔离记录，`reason` 是主因，`detail` 保留全部检出项，
因此「活动总数 = 可算数 + 隔离数」，且各原因计数之和等于隔离数。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class LiftIsolation(Base):
    __tablename__ = "lift_isolations"
    __table_args__ = (UniqueConstraint("run_id", "event_id", name="uq_lift_isolations_run_event"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("lift_runs.id", ondelete="CASCADE"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("price_events.id", ondelete="CASCADE"), index=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(24), index=True)
    start_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
