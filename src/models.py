from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class PriceCandle(BaseModel):
    timestamp: datetime; open: float; high: float; low: float; close: float; volume: int; ticker: str

class FundamentalSnapshot(BaseModel):
    ticker: str; market_cap: Optional[float]=None; pe_ratio: Optional[float]=None; promoter_holding: Optional[float]=None; fii_holding: Optional[float]=None; dii_holding: Optional[float]=None

class NewsItem(BaseModel):
    title: str; source: str