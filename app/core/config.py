from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_v1_prefix: str = "/api/v1"
    openclaw_api_key: str = Field(default="dev-openclaw-key")
    openclaw_enable_signature: bool = Field(default=False)
    openclaw_hmac_secret: str = Field(default="dev-secret")
    content_raw_dir: str = Field(default="content/reports/raw")
    content_rendered_dir: str = Field(default="content/reports/rendered")

    model_config = SettingsConfigDict(env_prefix="OPENCLAW_", env_file=".env", extra="ignore")


settings = Settings()
