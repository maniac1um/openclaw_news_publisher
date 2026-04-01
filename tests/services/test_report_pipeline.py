from app.schemas.report import OpenClawReportIn
from app.services.report_service import ReportService


def test_render_payload_shape() -> None:
    report = OpenClawReportIn.model_validate(
        {
            "task_id": "task-2",
            "keyword": "羽毛球",
            "time_range": {
                "start": "2026-03-01T00:00:00+00:00",
                "end": "2026-04-01T00:00:00+00:00",
            },
            "sources": ["source-a"],
            "items": [],
            "analysis": "analysis",
            "generated_title": "title",
            "generated_at": "2026-04-01T11:00:00+00:00",
        }
    )
    payload = ReportService().render_report_payload(ingest_id="ing-1", report=report)
    assert payload["ingest_id"] == "ing-1"
    assert payload["keyword"] == "羽毛球"
    assert payload["items_count"] == 0
