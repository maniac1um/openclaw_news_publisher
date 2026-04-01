import logging

from app.db.repositories import InMemoryIngestRepository
from app.schemas.report import OpenClawReportIn
from app.services.publish_service import PublishService
from app.services.report_service import ReportService

logger = logging.getLogger(__name__)


class JobRunner:
    def __init__(
        self,
        repo: InMemoryIngestRepository,
        report_service: ReportService,
        publish_service: PublishService,
    ) -> None:
        self.repo = repo
        self.report_service = report_service
        self.publish_service = publish_service

    def process_ingest(self, ingest_id: str, report: OpenClawReportIn) -> None:
        logger.info("ingest_id=%s stage=processing", ingest_id)
        self.repo.update_status(ingest_id, status="processing")
        try:
            rendered_payload = self.report_service.render_report_payload(ingest_id=ingest_id, report=report)
            rendered_path = self.report_service.persist_rendered(ingest_id=ingest_id, payload=rendered_payload)
            self.publish_service.trigger_publish(rendered_path=rendered_path)
            self.repo.update_status(ingest_id, status="published", rendered_path=rendered_path)
            logger.info("ingest_id=%s stage=published", ingest_id)
        except Exception as exc:  # pragma: no cover
            self.repo.update_status(ingest_id, status="failed", error=str(exc))
            logger.exception("ingest_id=%s stage=failed", ingest_id)
