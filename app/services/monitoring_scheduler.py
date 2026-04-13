import logging
from threading import Event, Thread

from app.services.monitoring_service import MonitoringService


logger = logging.getLogger(__name__)


class MonitoringScheduler:
    def __init__(
        self,
        database_url: str,
        monitor_id: str,
        interval_minutes: int,
        run_on_start: bool = False,
        *,
        allow_server_scrape: bool = False,
    ) -> None:
        self._service = MonitoringService(database_url, allow_server_scrape=allow_server_scrape)
        self._monitor_id = monitor_id
        self._interval_seconds = max(1, interval_minutes) * 60
        self._run_on_start = run_on_start
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._service.ensure_tables()
        self._thread = Thread(target=self._run_loop, name="monitoring-scheduler", daemon=True)
        self._thread.start()
        logger.info(
            "monitoring scheduler started monitor_id=%s interval_minutes=%s run_on_start=%s",
            self._monitor_id,
            self._interval_seconds // 60,
            self._run_on_start,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("monitoring scheduler stopped")

    def _run_loop(self) -> None:
        if self._run_on_start:
            self._run_once_safe()
        while not self._stop_event.wait(self._interval_seconds):
            self._run_once_safe()

    def _run_once_safe(self) -> None:
        try:
            result = self._service.run_once(self._monitor_id)
            logger.info(
                "monitoring scheduled run success monitor_id=%s total=%s ok=%s failed=%s",
                self._monitor_id,
                result.get("total_urls"),
                result.get("success_count"),
                result.get("failed_count"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("monitoring scheduled run failed monitor_id=%s error=%s", self._monitor_id, exc)
