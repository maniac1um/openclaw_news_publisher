from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


PlatformType = Literal[
    "taobao",
    "tmall",
    "jd",
    "news",
    "investing",
    "yahoo",
    "marketwatch",
    "sge",
    "eastmoney",
    "sina",
    "qq",
    "netease",
    "openclaw",
]


SourceProfileType = Literal["auto", "ecommerce", "commodity"]


class MonitoringBootstrapRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=100, description="监测关键词，例如：羽毛球价格")
    candidate_count: int = Field(default=20, ge=1, le=100, description="自动生成 URL 数量")
    platforms: list[PlatformType] = Field(
        default_factory=lambda: ["taobao", "tmall", "jd", "news"],
        description="参与生成候选 URL 的平台集合（仅 source_profile=ecommerce 或 auto 且推断为电商时生效）",
    )
    source_profile: SourceProfileType = Field(
        default="auto",
        description="auto：按关键词推断；ecommerce：淘宝/天猫/京东/资讯；commodity：黄金/原油等，候选 URL 以国内可访问的财经/上金所为主，不使用京东搜索",
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
    server_scrape_skipped: bool | None = Field(
        default=None,
        description="为 true 时表示未执行服务端网页抓取（由 OpenClaw 入库观测）",
    )
    detail: str | None = Field(default=None, description="补充说明，例如跳过抓取原因")


class MonitoringObservationIngestRequest(BaseModel):
    price: float = Field(description="OpenClaw 解析后的数值价格")
    title: str | None = Field(default=None, max_length=500)
    currency: str | None = Field(default="CNY", max_length=16)
    captured_at: datetime | None = Field(default=None, description="观测时间；省略则使用服务器当前时间")
    source_url: str | None = Field(default=None, max_length=2048, description="原始页面或数据源 URL")
    raw_payload: dict | None = Field(default=None, description="附加 JSON，会与入库元数据合并")


class MonitoringObservationIngestResponse(BaseModel):
    monitor_id: str
    observation_id: int
    monitor_url_id: int


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
    platform: PlatformType = Field(
        default="jd",
        description="入库平台标签；行情页请用 investing / yahoo / marketwatch 等",
    )


class MonitoringAddUrlsResponse(BaseModel):
    monitor_id: str
    inserted_urls: int
