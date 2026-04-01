import json
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, HTTPException, status

from app.core.config import settings
from app.db.models import IngestRecord
from app.db.repositories import InMemoryIngestRepository
from app.schemas.report import OpenClawReportIn
from app.workers.job_runner import JobRunner


class IntakeService:
    def __init__(self, repo: InMemoryIngestRepository, job_runner: JobRunner) -> None:
        self.repo = repo
        self.job_runner = job_runner
        self._raw_root = Path(settings.content_raw_dir)

    def ingest(
        self,
        report: OpenClawReportIn,
        request_id: str | None,
        background_tasks: BackgroundTasks,
    ) -> tuple[str, str]:
        if not request_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required header X-Request-Id",
            )

        duplicate = self.repo.get_by_request_and_task(request_id=request_id, task_id=report.task_id)
        if duplicate:
            return duplicate.ingest_id, duplicate.status

        ingest_id = str(uuid.uuid4())
        raw_path = self._persist_raw(ingest_id=ingest_id, report=report)
        record = IngestRecord(
            ingest_id=ingest_id,
            request_id=request_id,
            task_id=report.task_id,
            status="queued",
            raw_path=raw_path,
        )
        self.repo.create(record)
        background_tasks.add_task(self.job_runner.process_ingest, ingest_id, report)
        return ingest_id, "queued"

    def _persist_raw(self, ingest_id: str, report: OpenClawReportIn) -> str:
        self._raw_root.mkdir(parents=True, exist_ok=True)
        target = self._raw_root / f"{ingest_id}.json"
        target.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        return str(target)
