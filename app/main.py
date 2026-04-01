import logging

from fastapi import FastAPI

from app.api.v1.openclaw import router as openclaw_router
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="OpenClaw News Publisher")
app.include_router(openclaw_router, prefix=settings.api_v1_prefix)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
