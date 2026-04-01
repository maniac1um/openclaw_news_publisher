from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status

from app.core.security import verify_api_key, verify_optional_signature
from app.db.repositories import InMemoryIngestRepository
from app.schemas.report import IngestAccepted, IngestStatusResponse, OpenClawReportIn
from app.services.intake_service import IntakeService
from app.services.publish_service import PublishService
from app.services.report_service import ReportService
from app.workers.job_runner import JobRunner

router = APIRouter(prefix="/openclaw", tags=["openclaw"])

repo = InMemoryIngestRepository()
job_runner = JobRunner(repo=repo, report_service=ReportService(), publish_service=PublishService())
intake_service = IntakeService(repo=repo, job_runner=job_runner)


@router.post("/reports", response_model=IngestAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_report_ingest(
    request: Request,
    report: OpenClawReportIn,
    background_tasks: BackgroundTasks,
    x_request_id: str | None = Header(default=None),
    x_signature: str | None = Header(default=None),
    _: None = Depends(verify_api_key),
) -> IngestAccepted:
    verify_optional_signature(await request.body(), x_signature)
    ingest_id, ingest_status = intake_service.ingest(
        report=report,
        request_id=x_request_id,
        background_tasks=background_tasks,
    )
    return IngestAccepted(ingest_id=ingest_id, status=ingest_status)


@router.get("/reports/{ingest_id}", response_model=IngestStatusResponse)
def get_ingest_status(
    ingest_id: str,
    _: None = Depends(verify_api_key),
) -> IngestStatusResponse:
    record = repo.get_by_ingest_id(ingest_id=ingest_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingest not found")
    return IngestStatusResponse(
        ingest_id=record.ingest_id,
        request_id=record.request_id,
        task_id=record.task_id,
        status=record.status,
        raw_path=record.raw_path,
        rendered_path=record.rendered_path,
        error=record.error,
    )


@router.post("/reports/{ingest_id}/retry", response_model=IngestAccepted, status_code=status.HTTP_202_ACCEPTED)
def retry_ingest(
    ingest_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_api_key),
) -> IngestAccepted:
    record = repo.get_by_ingest_id(ingest_id=ingest_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingest not found")
    if record.status != "failed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only failed ingest can be retried")
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Retry payload hydration not implemented")
