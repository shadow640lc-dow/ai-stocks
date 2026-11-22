from typing import Optional

from pydantic import BaseModel, Field


class ScoutAlert(BaseModel):
    ticker: str = Field(..., min_length=1)
    action: Optional[str] = None
    price: Optional[float] = None
    timeframe: Optional[str] = None
    message: Optional[str] = None
    source: Optional[str] = "unknown"
    execute: bool = False
    qty: int = 0
    secret: str = Field(default="", max_length=256)
