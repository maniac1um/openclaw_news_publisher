from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_v1_prefix: str = "/api/v1"
    openclaw_api_key: str = Field(default="dev-openclaw-key")
    openclaw_enable_signature: bool = Field(default=False)
    openclaw_hmac_secret: str = Field(default="dev-secret")
    content_raw_dir: str = Field(default="content/reports/raw")
    content_rendered_dir: str = Field(default="content/reports/rendered")
    git_auto_push: bool = Field(default=False)
    git_remote: str = Field(default="origin")
    git_branch: str = Field(default="main")
    # Optional PostgreSQL DSN, for example:
    # postgresql://openclaw_app:password@127.0.0.1:5432/openclaw_app
    database_url: str | None = Field(default=None)
    # Optional PostgreSQL DSN dedicated to keyword monitoring.
    # Example: postgresql://openclaw_monitor:password@127.0.0.1:5432/openclaw_monitor
    monitoring_database_url: str | None = Field(default=None)
    # Optional PostgreSQL DSN dedicated to news library storage.
    # Example: postgresql://openclaw_news:password@127.0.0.1:5432/openclaw_news
    news_database_url: str | None = Field(default=None)
    # Internal scheduler for periodic monitoring run-once jobs.
    monitoring_scheduler_enabled: bool = Field(default=False)
    monitoring_scheduler_monitor_id: str | None = Field(default=None)
    monitoring_scheduler_interval_minutes: int = Field(default=1440)
    monitoring_scheduler_run_on_start: bool = Field(default=False)
    # OpenClaw Gateway WebSocket endpoint.
    # It is used by the chat proxy in `app/api/v1/chat.py`.
    openclaw_ws_url: str = Field(default="ws://localhost:18789/ws")

    model_config = SettingsConfigDict(env_prefix="OPENCLAW_", env_file=".env", extra="ignore")


settings = Settings()
