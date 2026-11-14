"""价格活动：一次促销的牌价 / 促销价 / 折扣 / 起止日 / 玩法。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class PriceEvent(Base):
    __tablename__ = "price_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_no: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(24), default="hypermarket")
    base_price: Mapped[float] = mapped_column(Float, default=0.0)
    promo_price: Mapped[float] = mapped_column(Float, default=0.0)
    discount: Mapped[float] = mapped_column(Float, default=0.0)
    start_on: Mapped[date] = mapped_column(Date, index=True)
    end_on: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(20), default="discount")
    note: Mapped[str] = mapped_column(String(200), default="")
    seed_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
