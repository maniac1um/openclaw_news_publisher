from fastapi.testclient import TestClient

from app.main import app


def _payload() -> dict:
    return {
        "task_id": "task-1",
        "keyword": "羽毛球",
        "time_range": {
            "start": "2026-03-01T00:00:00+00:00",
            "end": "2026-04-01T00:00:00+00:00",
        },
        "sources": ["source-a"],
        "items": [
            {
                "title": "x",
                "source": "source-a",
                "url": "https://example.com/1",
                "published_at": "2026-03-20T10:00:00+00:00",
                "price": 88.0,
                "currency": "CNY",
                "summary": "s",
            }
        ],
        "analysis": "a",
        "generated_title": "t",
        "generated_at": "2026-04-01T11:00:00+00:00",
    }


def test_post_and_get_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.publish_service.PublishService.trigger_publish",
        lambda self, rendered_path: None,
    )
    client = TestClient(app)
    headers = {"X-Api-Key": "dev-openclaw-key", "X-Request-Id": "req-1"}

    post_resp = client.post("/api/v1/openclaw/reports", headers=headers, json=_payload())
    assert post_resp.status_code == 202
    ingest_id = post_resp.json()["ingest_id"]

    get_resp = client.get(f"/api/v1/openclaw/reports/{ingest_id}", headers={"X-Api-Key": "dev-openclaw-key"})
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] in {"processing", "published", "queued"}


def test_idempotent_request(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.publish_service.PublishService.trigger_publish",
        lambda self, rendered_path: None,
    )
    client = TestClient(app)
    headers = {"X-Api-Key": "dev-openclaw-key", "X-Request-Id": "req-idem"}

    first = client.post("/api/v1/openclaw/reports", headers=headers, json=_payload()).json()
    second = client.post("/api/v1/openclaw/reports", headers=headers, json=_payload()).json()
    assert first["ingest_id"] == second["ingest_id"]
