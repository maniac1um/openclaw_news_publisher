from datetime import datetime

from pydantic import BaseModel, Field


class TimeRange(BaseModel):
    start: datetime
    end: datetime


class NewsItem(BaseModel):
    title: str
    source: str
    url: str
    published_at: datetime
    price: float | None = None
    currency: str | None = None
    summary: str | None = None


class OpenClawReportIn(BaseModel):
    task_id: str = Field(min_length=1)
    keyword: str = Field(min_length=1)
    time_range: TimeRange
    sources: list[str]
    items: list[NewsItem]
    analysis: str
    generated_title: str
    generated_at: datetime


class IngestAccepted(BaseModel):
    ingest_id: str
    status: str


class IngestStatusResponse(BaseModel):
    ingest_id: str
    request_id: str
    task_id: str
    status: str
    raw_path: str
    rendered_path: str | None = None
    error: str | None = None
