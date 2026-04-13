import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.error import URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# 命中则走「commodity」候选源（国际行情页），避免京东/淘宝搜索页误采商品价格
_COMMODITY_HINTS: tuple[str, ...] = (
    "黄金",
    "金价",
    "白银",
    "铂金",
    "钯金",
    "xau",
    "xag",
    "gold",
    "silver",
    "platinum",
    "比特币",
    "btc",
    "以太坊",
    "eth",
    "原油",
    "石油",
    "布伦特",
    "wti",
    "天然气",
    "铜价",
    "铝价",
    "大宗商品",
    "期货",
    "现货黄金",
    "国际金价",
)

# OpenClaw 外写入库时挂接的占位 URL（满足 monitor_url_id 外键；不用于服务端抓取）
_OPENCLAW_INGEST_PLATFORM = "openclaw"
_OPENCLAW_INGEST_URL = "https://openclaw.internal/ingest"

_COMMODITY_PLATFORMS: frozenset[str] = frozenset(
    {
        "investing",
        "yahoo",
        "marketwatch",
        "sge",
        "commodity",
        "eastmoney",
        "sina",
        "qq",
        "netease",
    }
)


class MonitoringService:
    def __init__(self, database_url: str, *, allow_server_scrape: bool = False) -> None:
        self.database_url = database_url
        self._allow_server_scrape = allow_server_scrape

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

    @staticmethod
    def _pick_commodity_price(candidates: list[float]) -> float | None:
        """行情页数字区间大、噪声多：取合理区间内的中位数，避免误选页脚小数字。"""
        if not candidates:
            return None
        filtered = sorted({round(v, 2) for v in candidates if 50.0 <= v <= 2_000_000.0})
        if not filtered:
            return None
        return filtered[len(filtered) // 2]

    @classmethod
    def infer_source_profile(cls, keyword: str) -> str:
        k = keyword.strip().lower()
        for hint in _COMMODITY_HINTS:
            if hint.lower() in k:
                return "commodity"
        return "ecommerce"

    @classmethod
    def _pick_price_for_platform(cls, candidates: list[float], platform: str) -> float | None:
        if platform in _COMMODITY_PLATFORMS:
            return cls._pick_commodity_price(candidates)
        return cls._pick_best_price(candidates)

    @classmethod
    def _extract_price(cls, html: str, platform: str) -> tuple[float | None, list[float]]:
        patterns_common = [
            r"(?:¥|￥|RMB\s*|CNY\s*|USD\s*\$?|\$)\s*(\d{1,7}(?:,\d{3})*(?:\.\d{1,4})?)",
            r"(\d{1,7}(?:,\d{3})*(?:\.\d{1,4})?)\s*(?:元|人民币)",
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
            "investing": [
                r'data-test="instrument-price-last"[^>]*>\s*([\d,\.]+)',
                r'"last"\s*:\s*"([\d,\.]+)"',
                r'"last":\s*([\d\.]+)',
                r'"price"\s*:\s*"([\d,\.]+)"',
            ],
            "yahoo": [
                r'"regularMarketPrice"\s*:\s*\{\s*"raw"\s*:\s*([\d\.]+)',
                r'"regularMarketPrice"\s*:\s*([\d\.]+)',
                r'"postMarketPrice"\s*:\s*\{\s*"raw"\s*:\s*([\d\.]+)',
            ],
            "marketwatch": [
                r'"Last"\s*:\s*([\d,\.]+)',
                r'"last"\s*:\s*([\d,\.]+)',
                r'intraday__price[^>]*>\s*\$?([\d,\.]+)',
            ],
            "sge": [
                r'(\d{3,5}(?:\.\d{2})?)\s*元\s*/\s*克',
                r'(\d{3,5}(?:\.\d{2})?)\s*元/克',
            ],
            "eastmoney": [
                r'"f43"\s*:\s*(\d+(?:\.\d+)?)',
                r'"f60"\s*:\s*(\d+(?:\.\d+)?)',
                r'"close"\s*:\s*(\d+(?:\.\d+)?)',
                r'"lastPrice"\s*:\s*(\d+(?:\.\d+)?)',
                r'"p"\s*:\s*(\d+(?:\.\d+)?)',
            ],
            "sina": [
                r'price["\']?\s*[:=]\s*["\']?(\d+(?:\.\d+)?)',
                r'(\d{3,5}(?:\.\d{2})?)\s*元/克',
            ],
            "qq": [
                r'"price"\s*:\s*(\d+(?:\.\d+)?)',
                r'"last"\s*:\s*"?(\d+(?:\.\d+)?)"?',
            ],
            "netease": [
                r'(\d{3,5}(?:\.\d{2})?)\s*元\s*/\s*克',
                r'"price"\s*:\s*(\d+(?:\.\d+)?)',
            ],
        }

        def _parse_num(s: str) -> float | None:
            t = s.replace(",", "").strip()
            try:
                return float(t)
            except ValueError:
                return None

        all_patterns = patterns_by_platform.get(platform, []) + patterns_common
        candidates: list[float] = []
        for pattern in all_patterns:
            for match in re.findall(pattern, html, flags=re.IGNORECASE):
                raw = match if isinstance(match, str) else match[0]
                v = _parse_num(raw)
                if v is not None:
                    candidates.append(v)
        picked = cls._pick_price_for_platform(candidates, platform)
        return picked, candidates

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

        # 资讯搜索使用「关键词+价格」，不再硬编码「羽毛球」（避免黄金等品类走错类目）
        news_baidu = [f"https://www.baidu.com/s?wd={term}%20%E4%BB%B7%E6%A0%BC" for term in query_pool]
        news_bing = [f"https://www.bing.com/search?q={term}+price" for term in query_pool]

        builders: dict[str, list[str]] = {
            "taobao": [f"https://s.taobao.com/search?q={term}" for term in query_pool],
            "tmall": [f"https://list.tmall.com/search_product.htm?q={term}" for term in query_pool],
            "jd": [f"https://search.jd.com/Search?keyword={term}" for term in query_pool],
            "news": news_baidu + news_bing,
        }

        out: list[tuple[str, str]] = []
        for platform in platforms:
            for url in builders.get(platform, []):
                if len(out) >= count:
                    return out
                out.append((platform, url))

        # 补足条数：若只选单一平台，则在该平台 URL 列表上循环，避免误混入其它平台（如仅 jd 却补出淘宝）。
        idx = 0
        fallback = [
            ("taobao", f"https://s.taobao.com/search?q={q}"),
            ("tmall", f"https://list.tmall.com/search_product.htm?q={q}"),
            ("jd", f"https://search.jd.com/Search?keyword={q}"),
        ]
        single_urls = builders.get(platforms[0], []) if len(platforms) == 1 else []
        while len(out) < count:
            if len(platforms) == 1 and single_urls:
                u = single_urls[len(out) % len(single_urls)]
                out.append((platforms[0], u))
            else:
                out.append(fallback[idx % len(fallback)])
                idx += 1
        return out[:count]

    @classmethod
    def generate_commodity_candidate_urls(cls, keyword: str, count: int) -> list[tuple[str, str]]:
        """黄金/原油等：候选 URL 以中国大陆通常可访问的站点为主（上金所、东方财富、新浪等），不含京东/淘宝及境外行情主站。"""
        k = quote_plus(keyword.strip())
        # 均为国内常见域名；个别页面若改版需用户通过 /urls 自行补链
        pool: list[tuple[str, str]] = [
            ("sge", "https://www.sge.com.cn/"),
            ("eastmoney", "https://data.eastmoney.com/cjsj/hjrgb.html"),
            ("eastmoney", "https://futures.eastmoney.com/qihuo/AU.html"),
            ("eastmoney", "https://futures.eastmoney.com/qihuo/AG.html"),
            ("eastmoney", "https://futures.eastmoney.com/qihuo/SC.html"),
            ("sina", "https://finance.sina.com.cn/nmetal/"),
            ("sina", "https://finance.sina.com.cn/futuremarket/"),
            ("qq", "https://finance.qq.com/"),
            ("netease", "https://money.163.com/"),
            ("commodity", f"https://www.baidu.com/s?wd={quote_plus(keyword + ' 黄金价格 今日')}"),
        ]
        out: list[tuple[str, str]] = []
        i = 0
        while len(out) < count and pool:
            out.append(pool[i % len(pool)])
            i += 1
        return out[:count]

    def bootstrap_monitor(
        self,
        keyword: str,
        candidate_count: int = 20,
        platforms: list[str] | None = None,
        cadence: str = "daily",
        source_profile: str = "auto",
    ) -> tuple[str, list[str]]:
        if not platforms:
            platforms = ["taobao", "tmall", "jd", "news"]
        resolved = source_profile.strip().lower() if source_profile else "auto"
        if resolved == "auto":
            resolved = self.infer_source_profile(keyword)
        if resolved not in ("ecommerce", "commodity"):
            resolved = "ecommerce"

        monitor_id = str(uuid.uuid4())
        discovered_at = _now_iso()
        if not self._allow_server_scrape:
            candidates = [(_OPENCLAW_INGEST_PLATFORM, _OPENCLAW_INGEST_URL)]
            meta_gen = "openclaw_external_placeholder_v1"
        elif resolved == "commodity":
            candidates = self.generate_commodity_candidate_urls(keyword=keyword, count=candidate_count)
            meta_gen = "openclaw_auto_commodity_v1"
        else:
            candidates = self.generate_candidate_urls(
                keyword=keyword, count=candidate_count, platforms=platforms
            )
            meta_gen = "openclaw_auto_ecommerce_v1"

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
                        json.dumps(
                            {
                                "generator": meta_gen,
                                "source_profile": resolved if self._allow_server_scrape else "openclaw_external",
                            },
                            ensure_ascii=False,
                        ),
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
            if not self._allow_server_scrape:
                return {
                    "monitor_id": monitor_id,
                    "total_urls": len(rows),
                    "success_count": 0,
                    "failed_count": 0,
                    "server_scrape_skipped": True,
                    "detail": "服务端网页抓取已关闭；请由 OpenClaw POST .../monitoring/{id}/observations/ingest 写入观测。",
                }
            scrape_rows = [(mid, p, u) for mid, p, u in rows if u != _OPENCLAW_INGEST_URL]
            if not scrape_rows:
                return {
                    "monitor_id": monitor_id,
                    "total_urls": 0,
                    "success_count": 0,
                    "failed_count": 0,
                    "server_scrape_skipped": True,
                    "detail": "仅存在 OpenClaw 占位 URL，无可抓取的外部链接；请追加真实 URL 或使用 observations/ingest。",
                }
            total = len(scrape_rows)
            for monitor_url_id, platform, url in scrape_rows:
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
            "server_scrape_skipped": False,
            "detail": None,
        }

    def ingest_openclaw_observation(
        self,
        monitor_id: str,
        *,
        price: float,
        title: str | None,
        currency: str | None,
        captured_at: datetime | None,
        source_url: str | None,
        raw_payload: dict | None,
    ) -> dict:
        sql_check = "SELECT 1 FROM price_monitors WHERE monitor_id = %s::uuid LIMIT 1"
        sql_sel_url = """
        SELECT id FROM price_monitor_urls
        WHERE monitor_id = %s::uuid AND url = %s
        LIMIT 1
        """
        sql_ins_url = """
        INSERT INTO price_monitor_urls (monitor_id, platform, url, discovered_at, metadata_json)
        VALUES (%s::uuid, %s, %s, NOW(), %s::jsonb)
        ON CONFLICT (monitor_id, url) DO NOTHING
        """
        sql_ins_obs = """
        INSERT INTO price_observations (
            monitor_id, monitor_url_id, captured_at, title, price, currency, status, error, raw_payload
        ) VALUES (%s::uuid, %s, %s, %s, %s, %s, 'ok', NULL, %s::jsonb)
        RETURNING id
        """
        merged: dict = {"ingest": "openclaw_post", "generator": "openclaw_external_v1"}
        if source_url:
            merged["source_url"] = source_url
        if raw_payload:
            merged.update(raw_payload)

        cap = captured_at if captured_at is not None else datetime.now(timezone.utc)
        if cap.tzinfo is None:
            cap = cap.replace(tzinfo=timezone.utc)

        curr = (currency or "CNY").strip() or "CNY"

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(sql_check, (monitor_id,))
            if not cur.fetchone():
                raise KeyError(monitor_id)
            cur.execute(sql_sel_url, (monitor_id, _OPENCLAW_INGEST_URL))
            row = cur.fetchone()
            if row:
                monitor_url_id = int(row[0])
            else:
                cur.execute(
                    sql_ins_url,
                    (
                        monitor_id,
                        _OPENCLAW_INGEST_PLATFORM,
                        _OPENCLAW_INGEST_URL,
                        json.dumps({"generator": "openclaw_external_url_v1"}, ensure_ascii=False),
                    ),
                )
                cur.execute(sql_sel_url, (monitor_id, _OPENCLAW_INGEST_URL))
                got = cur.fetchone()
                if not got:
                    raise RuntimeError("failed to resolve ingest placeholder monitor_url_id")
                monitor_url_id = int(got[0])
            cur.execute(
                sql_ins_obs,
                (
                    monitor_id,
                    monitor_url_id,
                    cap,
                    title,
                    price,
                    curr,
                    json.dumps(merged, ensure_ascii=False),
                ),
            )
            obs_row = cur.fetchone()
            if not obs_row:
                raise RuntimeError("insert observation returned no id")
            observation_id = int(obs_row[0])
            conn.commit()
        return {
            "monitor_id": monitor_id,
            "observation_id": observation_id,
            "monitor_url_id": monitor_url_id,
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
