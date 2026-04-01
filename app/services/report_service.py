import json
from pathlib import Path

from app.core.config import settings
from app.schemas.report import OpenClawReportIn


class ReportService:
    def __init__(self) -> None:
        self._rendered_root = Path(settings.content_rendered_dir)

    def render_report_payload(self, ingest_id: str, report: OpenClawReportIn) -> dict:
        return {
            "ingest_id": ingest_id,
            "title": report.generated_title,
            "keyword": report.keyword,
            "time_range": {
                "start": report.time_range.start.isoformat(),
                "end": report.time_range.end.isoformat(),
            },
            "analysis": report.analysis,
            "sources": report.sources,
            "items_count": len(report.items),
            "items": [item.model_dump(mode="json") for item in report.items],
            "generated_at": report.generated_at.isoformat(),
        }

    def persist_rendered(self, ingest_id: str, payload: dict) -> str:
        self._rendered_root.mkdir(parents=True, exist_ok=True)
        target = self._rendered_root / f"{ingest_id}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(target)
