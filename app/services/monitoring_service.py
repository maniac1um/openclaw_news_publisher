import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.error import URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MonitoringService:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url)

    def ensure_tables(self) -> None:
        sql_monitors = """
        CREATE TABLE IF NOT EXISTS price_monitors (
            monitor_id UUID PRIMARY KEY,
            keyword TEXT NOT NULL,
            cadence TEXT NOT NULL,
            source_mode TEXT NOT NULL DEFAULT 'openclaw_auto',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
        sql_urls = """
        CREATE TABLE IF NOT EXISTS price_monitor_urls (
            id BIGSERIAL PRIMARY KEY,
            monitor_id UUID NOT NULL REFERENCES price_monitors(monitor_id) ON DELETE CASCADE,
            platform TEXT NOT NULL,
            url TEXT NOT NULL,
            discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            UNIQUE (monitor_id, url)
        )
        """
        sql_observations = """
        CREATE TABLE IF NOT EXISTS price_observations (
            id BIGSERIAL PRIMARY KEY,
            monitor_id UUID NOT NULL REFERENCES price_monitors(monitor_id) ON DELETE CASCADE,
            monitor_url_id BIGINT NOT NULL REFERENCES price_monitor_urls(id) ON DELETE CASCADE,
            captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            title TEXT,
            price NUMERIC(12,2),
            currency TEXT,
            status TEXT NOT NULL,
            error TEXT,
            raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql_monitors)
            cur.execute(sql_urls)
            cur.execute(sql_observations)
            conn.commit()

    @staticmethod
    def _extract_title(html: str) -> str | None:
        match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        title = re.sub(r"\s+", " ", match.group(1)).strip()
        return title[:300] if title else None

    @staticmethod
    def _pick_best_price(candidates: list[float]) -> float | None:
        if not candidates:
            return None
        filtered = [value for value in candidates if 1.0 <= value <= 5000.0]
        if not filtered:
            return None
        filtered.sort()
        return filtered[0]

    @classmethod
    def _extract_price(cls, html: str, platform: str) -> tuple[float | None, list[float]]:
        patterns_common = [
            r"(?:¥|￥|RMB\s*|CNY\s*)(\d{1,6}(?:\.\d{1,2})?)",
            r"(\d{1,6}(?:\.\d{1,2})?)\s*(?:元|人民币)",
            r'"price"\s*:\s*"(\d{1,6}(?:\.\d{1,2})?)"',
            r'"currentPrice"\s*:\s*"(\d{1,6}(?:\.\d{1,2})?)"',
        ]
        patterns_by_platform = {
            "jd": [
                r'"p"\s*:\s*"(\d{1,6}(?:\.\d{1,2})?)"',
                r'"jdPrice"\s*:\s*"(\d{1,6}(?:\.\d{1,2})?)"',
            ],
            "taobao": [
                r'"view_price"\s*:\s*"(\d{1,6}(?:\.\d{1,2})?)"',
                r'"reserve_price"\s*:\s*"(\d{1,6}(?:\.\d{1,2})?)"',
            ],
            "tmall": [
                r'"promotionPrice"\s*:\s*"(\d{1,6}(?:\.\d{1,2})?)"',
                r'"price"\s*:\s*"(\d{1,6}(?:\.\d{1,2})?)"',
            ],
        }

        all_patterns = patterns_by_platform.get(platform, []) + patterns_common
        candidates: list[float] = []
        for pattern in all_patterns:
            for match in re.findall(pattern, html, flags=re.IGNORECASE):
                try:
                    candidates.append(float(match))
                except ValueError:
                    continue
        return cls._pick_best_price(candidates), candidates

    @staticmethod
    def generate_candidate_urls(keyword: str, count: int, platforms: list[str]) -> list[tuple[str, str]]:
        q = quote_plus(keyword.strip())
        base_queries = [
            keyword,
            f"{keyword} 尤尼克斯",
            f"{keyword} 李宁",
            f"{keyword} 亚狮龙",
            f"{keyword} 胜利",
        ]
        if "价格" not in keyword:
            base_queries.append(f"{keyword} 价格")
        query_pool = [quote_plus(item.strip()) for item in base_queries if item.strip()]

        builders: dict[str, list[str]] = {
            "taobao": [f"https://s.taobao.com/search?q={term}" for term in query_pool],
            "tmall": [f"https://list.tmall.com/search_product.htm?q={term}" for term in query_pool],
            "jd": [f"https://search.jd.com/Search?keyword={term}" for term in query_pool],
            "news": [
                f"https://www.baidu.com/s?wd={term}%20%E7%BE%BD%E6%AF%9B%E7%90%83%20%E4%BB%B7%E6%A0%BC"
                for term in query_pool
            ]
            + [
                f"https://www.bing.com/search?q={term}+%E7%BE%BD%E6%AF%9B%E7%90%83+%E4%BB%B7%E6%A0%BC"
                for term in query_pool
            ],
        }

        out: list[tuple[str, str]] = []
        for platform in platforms:
            for url in builders.get(platform, []):
                if len(out) >= count:
                    return out
                out.append((platform, url))

        # Guarantee count if platform-set is tiny.
        idx = 0
        fallback = [
            ("taobao", f"https://s.taobao.com/search?q={q}"),
            ("tmall", f"https://list.tmall.com/search_product.htm?q={q}"),
            ("jd", f"https://search.jd.com/Search?keyword={q}"),
        ]
        while len(out) < count:
            out.append(fallback[idx % len(fallback)])
            idx += 1
        return out[:count]

    def bootstrap_monitor(
        self,
        keyword: str,
        candidate_count: int = 20,
        platforms: list[str] | None = None,
        cadence: str = "daily",
    ) -> tuple[str, list[str]]:
        if not platforms:
            platforms = ["taobao", "tmall", "jd", "news"]
        monitor_id = str(uuid.uuid4())
        discovered_at = _now_iso()
        candidates = self.generate_candidate_urls(keyword=keyword, count=candidate_count, platforms=platforms)

        sql_monitor = """
        INSERT INTO price_monitors (monitor_id, keyword, cadence, source_mode, created_at)
        VALUES (%s::uuid, %s, %s, 'openclaw_auto', %s::timestamptz)
        """
        sql_url = """
        INSERT INTO price_monitor_urls (monitor_id, platform, url, discovered_at, metadata_json)
        VALUES (%s::uuid, %s, %s, %s::timestamptz, %s::jsonb)
        ON CONFLICT (monitor_id, url) DO NOTHING
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql_monitor, (monitor_id, keyword, cadence, discovered_at))
            for platform, url in candidates:
                cur.execute(
                    sql_url,
                    (
                        monitor_id,
                        platform,
                        url,
                        discovered_at,
                        json.dumps({"generator": "openclaw_auto_v1"}, ensure_ascii=False),
                    ),
                )
            conn.commit()
        return monitor_id, [url for _, url in candidates]

    def run_once(self, monitor_id: str, timeout_seconds: int = 12) -> dict:
        sql_get_urls = """
        SELECT id, platform, url
        FROM price_monitor_urls
        WHERE monitor_id = %s::uuid
        ORDER BY id ASC
        """
        sql_insert_observation = """
        INSERT INTO price_observations (
            monitor_id, monitor_url_id, captured_at, title, price, currency, status, error, raw_payload
        ) VALUES (%s::uuid, %s, NOW(), %s, %s, %s, %s, %s, %s::jsonb)
        """
        total = 0
        success = 0
        failed = 0
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql_get_urls, (monitor_id,))
            rows = cur.fetchall()
            if not rows:
                raise KeyError(monitor_id)
            total = len(rows)
            for monitor_url_id, platform, url in rows:
                title = None
                price = None
                error = None
                status = "ok"
                raw_payload: dict = {"platform": platform, "url": url}
                try:
                    req = Request(url, headers={"User-Agent": "Mozilla/5.0 OpenClaw-Monitor/1.0"})
                    with urlopen(req, timeout=timeout_seconds) as resp:
                        body = resp.read(400_000)
                        html = body.decode("utf-8", errors="ignore")
                        title = self._extract_title(html)
                        price, candidates = self._extract_price(html, platform=platform)
                        raw_payload["http_status"] = getattr(resp, "status", None)
                        raw_payload["content_preview"] = html[:600]
                        raw_payload["price_candidates"] = candidates[:20]
                except (TimeoutError, URLError, ValueError) as exc:
                    status = "error"
                    error = str(exc)
                except Exception as exc:  # noqa: BLE001
                    status = "error"
                    error = f"unexpected: {exc}"

                cur.execute(
                    sql_insert_observation,
                    (
                        monitor_id,
                        monitor_url_id,
                        title,
                        price,
                        "CNY" if price is not None else None,
                        status,
                        error,
                        json.dumps(raw_payload, ensure_ascii=False),
                    ),
                )
                if status == "ok":
                    success += 1
                else:
                    failed += 1
            conn.commit()
        return {
            "monitor_id": monitor_id,
            "total_urls": total,
            "success_count": success,
            "failed_count": failed,
        }

    def get_summary(self, monitor_id: str, window_days: int = 7) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=window_days)
        sql_keyword = "SELECT keyword FROM price_monitors WHERE monitor_id = %s::uuid LIMIT 1"
        sql_summary = """
        SELECT
            COUNT(*) AS total_observations,
            COUNT(price) AS priced_observations,
            MIN(price)::float8,
            MAX(price)::float8,
            AVG(price)::float8
        FROM price_observations
        WHERE monitor_id = %s::uuid
          AND captured_at >= %s::timestamptz
        """
        sql_latest = """
        SELECT price::float8
        FROM price_observations
        WHERE monitor_id = %s::uuid
          AND price IS NOT NULL
          AND captured_at >= %s::timestamptz
        ORDER BY captured_at DESC, id DESC
        LIMIT 1
        """
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql_keyword, (monitor_id,))
            key_row = cur.fetchone()
            if not key_row:
                raise KeyError(monitor_id)
            keyword = key_row[0]
            cur.execute(sql_summary, (monitor_id, since.isoformat()))
            total_observations, priced_observations, min_price, max_price, avg_price = cur.fetchone()
            cur.execute(sql_latest, (monitor_id, since.isoformat()))
            latest_row = cur.fetchone()
            latest_price = latest_row[0] if latest_row else None
        return {
            "monitor_id": monitor_id,
            "keyword": keyword,
            "window_days": window_days,
            "total_observations": int(total_observations or 0),
            "priced_observations": int(priced_observations or 0),
            "min_price": min_price,
            "max_price": max_price,
            "avg_price": avg_price,
            "latest_price": latest_price,
        }

    def add_urls(self, monitor_id: str, urls: list[str], platform: str) -> int:
        sql_check = "SELECT 1 FROM price_monitors WHERE monitor_id = %s::uuid LIMIT 1"
        sql_insert = """
        INSERT INTO price_monitor_urls (monitor_id, platform, url, discovered_at, metadata_json)
        VALUES (%s::uuid, %s, %s, NOW(), %s::jsonb)
        ON CONFLICT (monitor_id, url) DO NOTHING
        """
        inserted = 0
        cleaned = [item.strip() for item in urls if item and item.strip().startswith(("http://", "https://"))]
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql_check, (monitor_id,))
            if not cur.fetchone():
                raise KeyError(monitor_id)
            for url in cleaned:
                cur.execute(
                    sql_insert,
                    (
                        monitor_id,
                        platform,
                        url,
                        json.dumps({"generator": "manual_add_v1"}, ensure_ascii=False),
                    ),
                )
                if cur.rowcount > 0:
                    inserted += 1
            conn.commit()
        return inserted
