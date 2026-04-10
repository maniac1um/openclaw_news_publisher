from datetime import datetime

from pydantic import BaseModel, Field


class NewsLibraryIn(BaseModel):
    keyword: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1)
    source_url: str = Field(min_length=1, max_length=2000)
    title: str | None = Field(default=None, max_length=500)
    source_name: str | None = Field(default=None, max_length=200)
    published_at: datetime | None = None


class NewsLibraryCreated(BaseModel):
    id: int
    created_at: datetime


class NewsLibraryItem(BaseModel):
    id: int
    keyword: str
    summary: str
    source_url: str
    title: str | None = None
    source_name: str | None = None
    published_at: datetime | None = None
    created_at: datetime
