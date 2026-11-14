"""日销量事实表：POS / 渠道回传的一天一个 SKU 一条。"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class SalesDaily(Base):
    __tablename__ = "sales_daily"
    __table_args__ = (UniqueConstraint("sku_id", "sold_on", name="uq_sales_sku_day"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(24), default="hypermarket", index=True)
    sold_on: Mapped[date] = mapped_column(Date, index=True)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Float, default=0.0)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    is_promo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("price_events.id", ondelete="SET NULL"), nullable=True, index=True
    )
