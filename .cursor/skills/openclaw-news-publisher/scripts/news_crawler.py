#!/usr/bin/env python3
"""
Generic news crawler for OpenClaw News Publisher skill.

Design goals:
- No fixed sites: accepts URLs from CLI/config file.
- Easy to tweak: keep top-level defaults/variables obvious.
- Anti-crawl basics: UA rotation, jitter delay, retry/backoff.
- Produces OpenClaw-compatible report JSON.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


# ----------------------------
# Editable defaults
# ----------------------------
DEFAULT_SEED_URLS: list[str] = [
    # Fill your own URLs or use --urls/--config.
    # "https://example.com/news",
]
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MAX_PAGES = 30
DEFAULT_MAX_ITEMS = 20
DEFAULT_DELAY_RANGE_SECONDS = (1.0, 3.0)
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_BASE_SECONDS = 1.2
DEFAULT_DENY_URL_KEYWORDS = [
    "login",
    "signup",
    "account",
    "privacy",
    "terms",
    "mailto:",
    "javascript:",
]
DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


def _iso_utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _parse_dt(text: str | None) -> datetime | None:
    if not text:
        return None
    txt = text.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(txt)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.title: str = ""
        self.in_title = False
        self.meta: dict[str, str] = {}
        self.time_values: list[str] = []
        self.h1: str = ""
        self.in_h1 = False
        self.paragraphs: list[str] = []
        self.in_p = False
        self._buffer = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        m = dict(attrs)
        if tag == "a":
            href = m.get("href")
            if href:
                self.links.append(href)
        elif tag == "title":
            self.in_title = True
            self._buffer = []
        elif tag == "meta":
            k = (m.get("property") or m.get("name") or "").strip().lower()
            v = (m.get("content") or "").strip()
            if k and v:
                self.meta[k] = v
        elif tag == "time":
            dt = (m.get("datetime") or "").strip()
            if dt:
                self.time_values.append(dt)
        elif tag == "h1":
            self.in_h1 = True
            self._buffer = []
        elif tag == "p":
            self.in_p = True
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self.in_title:
            self.title = "".join(self._buffer).strip()
            self.in_title = False
        elif tag == "h1" and self.in_h1:
            self.h1 = "".join(self._buffer).strip()
            self.in_h1 = False
        elif tag == "p" and self.in_p:
            text = "".join(self._buffer).strip()
            if text:
                self.paragraphs.append(text)
            self.in_p = False
        self._buffer = []

    def handle_data(self, data: str) -> None:
        if self.in_title or self.in_h1 or self.in_p:
            self._buffer.append(data)


@dataclass
class CrawlConfig:
    keyword: str
    seed_urls: list[str]
    max_pages: int
    max_items: int
    timeout_seconds: int
    retries: int
    backoff_base_seconds: float
    delay_min: float
    delay_max: float
    include_domains: set[str]
    deny_url_keywords: list[str]
    earliest_time: datetime | None


def _normalize_url(url: str) -> str:
    return url.strip()


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def _is_likely_article_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    if re.search(r"/(news|article|post|detail|story)/", path):
        return True
    # Many sites use yyyy/mm/dd in article URLs.
    if re.search(r"/20\d{2}/\d{1,2}/\d{1,2}/", path):
        return True
    return False


def _fetch_html(url: str, cfg: CrawlConfig) -> str | None:
    last_err = None
    for attempt in range(cfg.retries):
        req = Request(
            url,
            headers={
                "User-Agent": random.choice(DEFAULT_USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
            },
        )
        try:
            with urlopen(req, timeout=cfg.timeout_seconds) as resp:
                charset = "utf-8"
                content_type = resp.headers.get("Content-Type", "")
                m = re.search(r"charset=([^\s;]+)", content_type, re.IGNORECASE)
                if m:
                    charset = m.group(1).strip().strip('"').strip("'")
                data = resp.read()
                return data.decode(charset, errors="replace")
        except Exception as exc:
            last_err = exc
            backoff = cfg.backoff_base_seconds * (2**attempt) + random.uniform(0, 0.6)
            time.sleep(backoff)
    print(f"[warn] fetch failed: {url} ({last_err})")
    return None


def _extract_article(url: str, html: str, keyword: str) -> dict | None:
    p = LinkParser()
    try:
        p.feed(html)
    except Exception:
        return None

    title = p.meta.get("og:title") or p.meta.get("twitter:title") or p.h1 or p.title
    title = unescape((title or "").strip())
    if not title:
        return None

    summary = (
        p.meta.get("description")
        or p.meta.get("og:description")
        or (p.paragraphs[0] if p.paragraphs else "")
    )
    summary = unescape((summary or "").strip())

    published_raw = (
        p.meta.get("article:published_time")
        or p.meta.get("published_time")
        or (p.time_values[0] if p.time_values else "")
    )
    published_dt = _parse_dt(published_raw) or datetime.now(UTC)

    return {
        "title": title,
        "source": _domain(url),
        "url": url,
        "published_at": published_dt.isoformat(),
        "price": None,
        "currency": None,
        "summary": summary or f"围绕关键词“{keyword}”的网页新闻条目。",
    }


def _iter_seed_urls(args: argparse.Namespace, config_json: dict) -> list[str]:
    seeds: list[str] = []
    seeds.extend(config_json.get("seed_urls") or [])
    seeds.extend(args.urls or [])
    if args.urls_file:
        for line in Path(args.urls_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                seeds.append(line)
    if not seeds:
        seeds.extend(DEFAULT_SEED_URLS)
    return [_normalize_url(u) for u in seeds if u.strip()]


def _build_config(args: argparse.Namespace) -> CrawlConfig:
    config_json: dict = {}
    if args.config:
        config_json = json.loads(Path(args.config).read_text(encoding="utf-8"))

    seed_urls = _iter_seed_urls(args, config_json)
    if not seed_urls:
        raise ValueError("No seed URLs provided. Use --urls or --config.")

    include_domains = set(config_json.get("include_domains") or [])
    if not include_domains:
        include_domains = {_domain(u) for u in seed_urls}

    delay_range = config_json.get("delay_range_seconds") or list(DEFAULT_DELAY_RANGE_SECONDS)
    delay_min = float(delay_range[0])
    delay_max = float(delay_range[1])

    hours_back = int(args.hours_back)
    earliest_time = datetime.now(UTC) - timedelta(hours=hours_back) if hours_back > 0 else None

    return CrawlConfig(
        keyword=args.keyword,
        seed_urls=seed_urls,
        max_pages=int(args.max_pages or config_json.get("max_pages") or DEFAULT_MAX_PAGES),
        max_items=int(args.max_items or config_json.get("max_items") or DEFAULT_MAX_ITEMS),
        timeout_seconds=int(config_json.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS),
        retries=int(config_json.get("retries") or DEFAULT_RETRIES),
        backoff_base_seconds=float(config_json.get("backoff_base_seconds") or DEFAULT_BACKOFF_BASE_SECONDS),
        delay_min=delay_min,
        delay_max=delay_max,
        include_domains=include_domains,
        deny_url_keywords=list(config_json.get("deny_url_keywords") or DEFAULT_DENY_URL_KEYWORDS),
        earliest_time=earliest_time,
    )


def crawl(cfg: CrawlConfig) -> dict:
    q: deque[str] = deque(cfg.seed_urls)
    seen: set[str] = set()
    items: list[dict] = []
    sources: set[str] = set()
    pages = 0

    while q and pages < cfg.max_pages and len(items) < cfg.max_items:
        url = q.popleft()
        if url in seen:
            continue
        seen.add(url)
        if any(k in url.lower() for k in cfg.deny_url_keywords):
            continue
        if _domain(url) not in cfg.include_domains:
            continue

        html = _fetch_html(url, cfg)
        pages += 1
        if not html:
            continue

        if _is_likely_article_url(url):
            article = _extract_article(url, html, cfg.keyword)
            if article:
                dt = _parse_dt(article.get("published_at"))
                if cfg.earliest_time and dt and dt < cfg.earliest_time:
                    pass
                else:
                    items.append(article)
                    sources.add(article["source"])

        parser = LinkParser()
        try:
            parser.feed(html)
        except Exception:
            parser = None
        if parser:
            for href in parser.links:
                abs_url = urljoin(url, href)
                if abs_url.startswith("http") and abs_url not in seen:
                    if _domain(abs_url) in cfg.include_domains:
                        q.append(abs_url)

        time.sleep(random.uniform(cfg.delay_min, cfg.delay_max))

    now_iso = _iso_utc_now()
    start_iso = (cfg.earliest_time.isoformat() if cfg.earliest_time else now_iso)
    report = {
        "task_id": f"crawl-{uuid.uuid4().hex[:12]}",
        "keyword": cfg.keyword,
        "time_range": {"start": start_iso, "end": now_iso},
        "sources": sorted(sources) if sources else sorted({_domain(u) for u in cfg.seed_urls}),
        "items": items,
        "analysis": (
            f"自动抓取得到 {len(items)} 条与“{cfg.keyword}”相关的网页新闻。"
            "建议由 OpenClaw 进一步做去重、事实核验与趋势归纳。"
        ),
        "generated_title": f"{cfg.keyword} 相关新闻抓取汇总",
        "generated_at": now_iso,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generic anti-crawl news scraper for OpenClaw report payload.")
    parser.add_argument("--keyword", required=True, help="Report keyword, e.g. 羽毛球")
    parser.add_argument("--urls", nargs="*", default=[], help="Seed URLs (can pass multiple)")
    parser.add_argument("--urls-file", help="Text file with one URL per line")
    parser.add_argument("--config", help="Optional JSON config file")
    parser.add_argument("--hours-back", type=int, default=72, help="Only keep items newer than N hours (0=disable)")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="Max pages to visit")
    parser.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS, help="Max article items to keep")
    parser.add_argument("--output", default="report_payload.json", help="Output JSON path")
    args = parser.parse_args()

    cfg = _build_config(args)
    report = crawl(cfg)

    out = Path(args.output)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] wrote report JSON: {out}")
    print(f"[ok] items: {len(report.get('items') or [])}, sources: {len(report.get('sources') or [])}")


if __name__ == "__main__":
    main()

