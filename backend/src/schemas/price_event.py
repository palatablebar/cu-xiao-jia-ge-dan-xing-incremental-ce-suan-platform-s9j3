from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class PriceEventIn(BaseModel):
    event_no: str = Field(min_length=4, max_length=24, pattern=r"^PE-[0-9]{3,6}$")
    sku_id: int = Field(gt=0)
    channel: str | None = None
    base_price: float | None = Field(default=None, gt=0, le=100000)
    promo_price: float = Field(gt=0, le=100000)
    start_on: date
    end_on: date
    kind: str = "discount"
    note: str | None = Field(default=None, max_length=200)


class PriceEventPatch(BaseModel):
    channel: str | None = None
    base_price: float | None = Field(default=None, gt=0, le=100000)
    promo_price: float | None = Field(default=None, gt=0, le=100000)
    start_on: date | None = None
    end_on: date | None = None
    kind: str | None = None
    note: str | None = Field(default=None, max_length=200)
