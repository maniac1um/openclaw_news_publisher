from typing import Literal

from pydantic import BaseModel, Field


PlatformType = Literal["taobao", "tmall", "jd", "news"]


class MonitoringBootstrapRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=100, description="监测关键词，例如：羽毛球价格")
    candidate_count: int = Field(default=20, ge=1, le=100, description="自动生成 URL 数量")
    platforms: list[PlatformType] = Field(
        default_factory=lambda: ["taobao", "tmall", "jd", "news"],
        description="参与生成候选 URL 的平台集合",
    )
    cadence: str = Field(default="daily", min_length=1, max_length=20, description="采集频率标识")


class MonitoringBootstrapResponse(BaseModel):
    monitor_id: str
    keyword: str
    inserted_urls: int
    urls: list[str]


class MonitoringRunOnceResponse(BaseModel):
    monitor_id: str
    total_urls: int
    success_count: int
    failed_count: int


class MonitoringSummaryResponse(BaseModel):
    monitor_id: str
    keyword: str
    window_days: int
    total_observations: int
    priced_observations: int
    min_price: float | None
    max_price: float | None
    avg_price: float | None
    latest_price: float | None


class MonitoringAddUrlsRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=100)
    platform: PlatformType = Field(default="jd")


class MonitoringAddUrlsResponse(BaseModel):
    monitor_id: str
    inserted_urls: int
