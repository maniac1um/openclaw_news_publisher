from dataclasses import dataclass, field
from datetime import datetime, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class IngestRecord:
    ingest_id: str
    request_id: str
    task_id: str
    status: str
    raw_path: str
    rendered_path: str | None = None
    error: str | None = None
    keyword: str | None = None
    generated_title: str | None = None
    generated_at: datetime | None = None
    created_at: datetime = field(default_factory=now_utc)
    updated_at: datetime = field(default_factory=now_utc)
