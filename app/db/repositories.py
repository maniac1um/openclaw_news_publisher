from threading import Lock

from app.db.models import IngestRecord, now_utc


class InMemoryIngestRepository:
    def __init__(self) -> None:
        self._by_ingest_id: dict[str, IngestRecord] = {}
        self._by_idempotency_key: dict[str, str] = {}
        self._lock = Lock()

    @staticmethod
    def _idem_key(request_id: str, task_id: str) -> str:
        return f"{request_id}:{task_id}"

    def get_by_ingest_id(self, ingest_id: str) -> IngestRecord | None:
        return self._by_ingest_id.get(ingest_id)

    def get_by_request_and_task(self, request_id: str, task_id: str) -> IngestRecord | None:
        ingest_id = self._by_idempotency_key.get(self._idem_key(request_id, task_id))
        if not ingest_id:
            return None
        return self._by_ingest_id.get(ingest_id)

    def create(self, record: IngestRecord) -> IngestRecord:
        with self._lock:
            self._by_ingest_id[record.ingest_id] = record
            self._by_idempotency_key[self._idem_key(record.request_id, record.task_id)] = record.ingest_id
        return record

    def update_status(
        self,
        ingest_id: str,
        status: str,
        rendered_path: str | None = None,
        error: str | None = None,
    ) -> IngestRecord:
        record = self._by_ingest_id[ingest_id]
        record.status = status
        if rendered_path is not None:
            record.rendered_path = rendered_path
        record.error = error
        record.updated_at = now_utc()
        return record
