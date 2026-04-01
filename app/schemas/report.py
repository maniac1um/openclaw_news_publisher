from datetime import datetime

from pydantic import BaseModel, Field


class TimeRange(BaseModel):
    start: datetime = Field(description="采集时间范围起点（ISO 8601）")
    end: datetime = Field(description="采集时间范围终点（ISO 8601）")


class NewsItem(BaseModel):
    title: str = Field(description="新闻标题")
    source: str = Field(description="来源站点或媒体名")
    url: str = Field(description="原文链接")
    published_at: datetime = Field(description="发布时间（ISO 8601）")
    price: float | None = Field(default=None, description="提取到的价格（可选）")
    currency: str | None = Field(default=None, description="币种（可选）")
    summary: str | None = Field(default=None, description="摘要（可选）")


class OpenClawReportIn(BaseModel):
    task_id: str = Field(min_length=1, description="OpenClaw 任务 ID")
    keyword: str = Field(min_length=1, description="查询关键词，例如：羽毛球")
    time_range: TimeRange = Field(description="采集时间范围")
    sources: list[str] = Field(description="来源列表")
    items: list[NewsItem] = Field(description="抽取后的结构化条目")
    analysis: str = Field(description="模型生成的分析结论")
    generated_title: str = Field(description="生成的报告标题")
    generated_at: datetime = Field(description="报告生成时间（ISO 8601）")


class IngestAccepted(BaseModel):
    ingest_id: str = Field(description="入站记录 ID")
    status: str = Field(description="当前状态，例如 queued")


class IngestStatusResponse(BaseModel):
    ingest_id: str = Field(description="入站记录 ID")
    request_id: str = Field(description="请求幂等键")
    task_id: str = Field(description="OpenClaw 任务 ID")
    status: str = Field(description="任务状态：queued/processing/published/failed")
    raw_path: str = Field(description="原始入站数据路径")
    rendered_path: str | None = Field(default=None, description="渲染后数据路径")
    error: str | None = Field(default=None, description="失败原因")
