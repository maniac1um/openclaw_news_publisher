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
        rendered_payload: dict | None = None,
    ) -> IngestRecord:
        record = self._by_ingest_id[ingest_id]
        record.status = status
        if rendered_path is not None:
            record.rendered_path = rendered_path
        record.error = error
        record.updated_at = now_utc()
        return record


class PostgresIngestRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url)

    @staticmethod
    def _row_to_record(row: tuple) -> IngestRecord:
        ingest_id, task_id, status, payload_json = row
        payload_json = payload_json or {}
        return IngestRecord(
            ingest_id=str(ingest_id),
            request_id=str(payload_json.get("request_id") or ""),
            task_id=str(task_id),
            status=str(status),
            raw_path=str(payload_json.get("raw_path") or ""),
            rendered_path=payload_json.get("rendered_path"),
            error=payload_json.get("error"),
        )

    def get_by_ingest_id(self, ingest_id: str) -> IngestRecord | None:
        sql = """
        SELECT ingest_id, task_id, status, payload_json
        FROM reports
        WHERE ingest_id = %s::uuid
        LIMIT 1
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (ingest_id,))
            row = cur.fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def get_by_request_and_task(self, request_id: str, task_id: str) -> IngestRecord | None:
        sql = """
        SELECT ingest_id, task_id, status, payload_json
        FROM reports
        WHERE task_id = %s
          AND payload_json->>'request_id' = %s
        ORDER BY id DESC
        LIMIT 1
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (task_id, request_id))
            row = cur.fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def create(self, record: IngestRecord) -> IngestRecord:
        sql = """
        INSERT INTO reports (
            ingest_id,
            task_id,
            keyword,
            status,
            generated_title,
            generated_at,
            payload_json,
            updated_at
        ) VALUES (%s::uuid, %s, %s, %s, %s, %s, %s::jsonb, NOW())
        """
        payload_json = {
            "request_id": record.request_id,
            "raw_path": record.raw_path,
            "rendered_path": record.rendered_path,
            "error": record.error,
            "report": None,
        }
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    record.ingest_id,
                    record.task_id,
                    record.keyword or "unknown",
                    record.status,
                    record.generated_title or "",
                    record.generated_at,
                    __import__("json").dumps(payload_json, ensure_ascii=False),
                ),
            )
            conn.commit()
        return record

    def update_status(
        self,
        ingest_id: str,
        status: str,
        rendered_path: str | None = None,
        error: str | None = None,
        rendered_payload: dict | None = None,
    ) -> IngestRecord:
        import json

        current = self.get_by_ingest_id(ingest_id)
        if not current:
            raise KeyError(ingest_id)

        sql = """
        UPDATE reports
        SET status = %s,
            payload_json = payload_json
              || jsonb_build_object('rendered_path', to_jsonb(%s::text))
              || jsonb_build_object('error', to_jsonb(%s::text))
              || jsonb_build_object('rendered_payload', %s::jsonb),
            updated_at = NOW()
        WHERE ingest_id = %s::uuid
        """
        rendered_payload_json = json.dumps(rendered_payload, ensure_ascii=False) if rendered_payload is not None else "null"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (status, rendered_path, error, rendered_payload_json, ingest_id))
            conn.commit()
        updated = self.get_by_ingest_id(ingest_id)
        if not updated:
            raise KeyError(ingest_id)
        return updated
