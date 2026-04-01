# News Pipeline Architecture

## Layers

- API layer (`app/api/v1/openclaw.py`)
- Intake and orchestration (`app/services/intake_service.py`)
- Processing worker (`app/workers/job_runner.py`)
- Data and persistence (`app/db/*`, `content/reports/*`)
- Publish adapter (`app/services/publish_service.py`, `scripts/publish_site.py`)

## Runtime Flow

1. OpenClaw POSTs report JSON to `/api/v1/openclaw/reports`.
2. API validates auth, schema, and request id.
3. Intake service enforces idempotency with `X-Request-Id + task_id`.
4. Raw payload is persisted into `content/reports/raw/`.
5. Background worker normalizes payload and writes to `content/reports/rendered/`.
6. Publish service triggers site publish script.
7. Final status is updated to `published` or `failed`.

## Storage Strategy

- Raw payload: traceability and replay support.
- Rendered payload: stable schema for site rendering.
