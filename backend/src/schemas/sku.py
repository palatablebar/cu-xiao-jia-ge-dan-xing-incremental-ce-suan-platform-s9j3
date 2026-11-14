from __future__ import annotations

from pydantic import BaseModel, Field


class SkuIn(BaseModel):
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Z][A-Z0-9]{1,19}$")
    name: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=2, max_length=40)
    spec: str | None = Field(default=None, max_length=40)
    channel: str = "hypermarket"
    cost: float = Field(ge=0, le=100000)
    list_price: float = Field(gt=0, le=100000)


class SkuPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    category: str | None = Field(default=None, min_length=2, max_length=40)
    spec: str | None = Field(default=None, max_length=40)
    channel: str | None = None
    cost: float | None = Field(default=None, ge=0, le=100000)
    list_price: float | None = Field(default=None, gt=0, le=100000)
    enabled: bool | None = None
