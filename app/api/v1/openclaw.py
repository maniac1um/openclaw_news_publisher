from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status

from app.core.config import settings
from app.core.security import verify_api_key, verify_optional_signature
from app.db.repositories import InMemoryIngestRepository, PostgresIngestRepository
from app.schemas.monitoring import (
    MonitoringAddUrlsRequest,
    MonitoringAddUrlsResponse,
    MonitoringBootstrapRequest,
    MonitoringBootstrapResponse,
    MonitoringRunOnceResponse,
    MonitoringSummaryResponse,
)
from app.schemas.report import IngestAccepted, IngestStatusResponse, OpenClawReportIn
from app.services.intake_service import IntakeService
from app.services.monitoring_service import MonitoringService
from app.services.publish_service import PublishService
from app.services.report_service import ReportService
from app.workers.job_runner import JobRunner

router = APIRouter(
    prefix="/openclaw",
    tags=["OpenClaw 接入"],
)

repo = PostgresIngestRepository(settings.database_url) if settings.database_url else InMemoryIngestRepository()
job_runner = JobRunner(repo=repo, report_service=ReportService(), publish_service=PublishService())
intake_service = IntakeService(repo=repo, job_runner=job_runner)


@router.post(
    "/reports",
    response_model=IngestAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="上报 OpenClaw 报告",
    description="接收 OpenClaw 发送的结构化报告 JSON，校验后入队异步处理。",
)
async def create_report_ingest(
    request: Request,
    report: OpenClawReportIn,
    background_tasks: BackgroundTasks,
    x_request_id: str | None = Header(default=None, description="请求幂等键，请求重试时保持一致。"),
    x_signature: str | None = Header(default=None, description="可选签名；开启签名校验时必填。"),
    _: None = Depends(verify_api_key),
) -> IngestAccepted:
    verify_optional_signature(await request.body(), x_signature)
    ingest_id, ingest_status = intake_service.ingest(
        report=report,
        request_id=x_request_id,
        background_tasks=background_tasks,
    )
    return IngestAccepted(ingest_id=ingest_id, status=ingest_status)


@router.get(
    "/reports/{ingest_id}",
    response_model=IngestStatusResponse,
    summary="查询处理状态",
    description="根据 ingest_id 查询任务状态与产物路径。",
)
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


@router.post(
    "/reports/{ingest_id}/retry",
    response_model=IngestAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="重试失败任务（预留）",
    description="仅允许对失败任务发起重试。当前为预留接口。",
)
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


@router.post(
    "/monitoring/bootstrap",
    response_model=MonitoringBootstrapResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建关键词监测并自动生成候选 URL",
    description="使用关键词自动生成候选 URL（淘宝/天猫/京东/资讯），并写入监测数据库。",
)
def bootstrap_monitoring(
    payload: MonitoringBootstrapRequest,
    _: None = Depends(verify_api_key),
) -> MonitoringBootstrapResponse:
    if not settings.monitoring_database_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="未配置 OPENCLAW_MONITORING_DATABASE_URL。",
        )
    service = MonitoringService(settings.monitoring_database_url)
    service.ensure_tables()
    monitor_id, urls = service.bootstrap_monitor(
        keyword=payload.keyword,
        candidate_count=payload.candidate_count,
        platforms=payload.platforms,
        cadence=payload.cadence,
    )
    return MonitoringBootstrapResponse(
        monitor_id=monitor_id,
        keyword=payload.keyword,
        inserted_urls=len(urls),
        urls=urls,
    )


@router.post(
    "/monitoring/{monitor_id}/run-once",
    response_model=MonitoringRunOnceResponse,
    status_code=status.HTTP_200_OK,
    summary="执行一次监测采样并写入 observations",
    description="遍历 monitor 下 URL，抓取页面标题/价格并入库 price_observations。",
)
def run_monitoring_once(
    monitor_id: str,
    _: None = Depends(verify_api_key),
) -> MonitoringRunOnceResponse:
    if not settings.monitoring_database_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="未配置 OPENCLAW_MONITORING_DATABASE_URL。",
        )
    service = MonitoringService(settings.monitoring_database_url)
    service.ensure_tables()
    try:
        result = service.run_once(monitor_id=monitor_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    return MonitoringRunOnceResponse(**result)


@router.get(
    "/monitoring/{monitor_id}/summary",
    response_model=MonitoringSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="查询监测窗口期摘要",
    description="返回最近 N 天的观测数量和价格统计。",
)
def get_monitoring_summary(
    monitor_id: str,
    window_days: int = 7,
    _: None = Depends(verify_api_key),
) -> MonitoringSummaryResponse:
    if not settings.monitoring_database_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="未配置 OPENCLAW_MONITORING_DATABASE_URL。",
        )
    service = MonitoringService(settings.monitoring_database_url)
    service.ensure_tables()
    try:
        result = service.get_summary(monitor_id=monitor_id, window_days=window_days)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    return MonitoringSummaryResponse(**result)


@router.post(
    "/monitoring/{monitor_id}/urls",
    response_model=MonitoringAddUrlsResponse,
    status_code=status.HTTP_200_OK,
    summary="为监测任务追加 URL",
    description="用于手工补充商品详情页 URL，提升价格抽取命中率。",
)
def add_monitoring_urls(
    monitor_id: str,
    payload: MonitoringAddUrlsRequest,
    _: None = Depends(verify_api_key),
) -> MonitoringAddUrlsResponse:
    if not settings.monitoring_database_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="未配置 OPENCLAW_MONITORING_DATABASE_URL。",
        )
    service = MonitoringService(settings.monitoring_database_url)
    service.ensure_tables()
    try:
        inserted = service.add_urls(monitor_id=monitor_id, urls=payload.urls, platform=payload.platform)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    return MonitoringAddUrlsResponse(monitor_id=monitor_id, inserted_urls=inserted)


@router.get(
    "/monitoring/scheduler/status",
    status_code=status.HTTP_200_OK,
    summary="查询内部监测定时任务状态",
    description="返回内部 scheduler 的配置与当前启动状态。",
)
def get_monitoring_scheduler_status(
    request: Request,
    _: None = Depends(verify_api_key),
) -> dict:
    started = bool(getattr(request.app.state, "monitoring_scheduler_started", False))
    has_db = bool(settings.monitoring_database_url)
    has_monitor = bool(settings.monitoring_scheduler_monitor_id)
    return {
        "mode": "internal",
        "enabled": settings.monitoring_scheduler_enabled,
        "started": started,
        "configured": settings.monitoring_scheduler_enabled and has_db and has_monitor,
        "monitor_id": settings.monitoring_scheduler_monitor_id,
        "interval_minutes": settings.monitoring_scheduler_interval_minutes,
        "run_on_start": settings.monitoring_scheduler_run_on_start,
        "has_monitoring_database_url": has_db,
    }
