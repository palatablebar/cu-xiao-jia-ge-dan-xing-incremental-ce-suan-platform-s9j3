from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LiftRunIn(BaseModel):
    trigger: Literal["manual", "schedule", "seed"] = "manual"
    pre_days: int = Field(default=14, ge=7, le=30)
    note: str | None = Field(default=None, max_length=200)


class ReviewIn(BaseModel):
    status: Literal["pending", "confirmed", "dismissed"]
    note: str | None = Field(default=None, max_length=1000)
