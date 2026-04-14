import logging
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from app.api.v1.openclaw import intake_service, router as openclaw_router
from app.api.v1.chat import router as chat_router
from app.core.config import settings
from app.core.security import verify_api_key
from app.schemas.report import OpenClawReportIn
from app.services.monitoring_scheduler import MonitoringScheduler
from app.services.monitoring_service import MonitoringService
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title="OpenClaw 新闻发布服务",
    description="接收 OpenClaw 生成的新闻分析结果，完成入站、处理与发布。",
    version="0.1.0",
)
app.include_router(openclaw_router, prefix=settings.api_v1_prefix)
app.include_router(chat_router, prefix=settings.api_v1_prefix)
app.state.monitoring_scheduler_started = False
app.state.external_scheduler_jobs = {}

_monitoring_scheduler: MonitoringScheduler | None = None


@app.on_event("startup")
def _start_monitoring_scheduler() -> None:
    global _monitoring_scheduler
    if not settings.monitoring_scheduler_enabled:
        app.state.monitoring_scheduler_started = False
        return
    if not settings.monitoring_database_url:
        logging.getLogger(__name__).warning(
            "monitoring scheduler enabled but OPENCLAW_MONITORING_DATABASE_URL is not set; skip starting scheduler"
        )
        app.state.monitoring_scheduler_started = False
        return
    if not settings.monitoring_scheduler_monitor_id:
        logging.getLogger(__name__).warning(
            "monitoring scheduler enabled but OPENCLAW_MONITORING_SCHEDULER_MONITOR_ID is not set; skip starting scheduler"
        )
        app.state.monitoring_scheduler_started = False
        return
    if not settings.monitoring_allow_server_scrape:
        logging.getLogger(__name__).warning(
            "monitoring scheduler skipped: OPENCLAW_MONITORING_ALLOW_SERVER_SCRAPE is false; "
            "internal run-once would not fetch URLs — use OpenClaw POST observations/ingest"
        )
        app.state.monitoring_scheduler_started = False
        return
    _monitoring_scheduler = MonitoringScheduler(
        database_url=settings.monitoring_database_url,
        monitor_id=settings.monitoring_scheduler_monitor_id,
        interval_minutes=settings.monitoring_scheduler_interval_minutes,
        run_on_start=settings.monitoring_scheduler_run_on_start,
        allow_server_scrape=settings.monitoring_allow_server_scrape,
    )
    _monitoring_scheduler.start()
    app.state.monitoring_scheduler_started = True


@app.on_event("shutdown")
def _stop_monitoring_scheduler() -> None:
    global _monitoring_scheduler
    if _monitoring_scheduler is None:
        app.state.monitoring_scheduler_started = False
        return
    _monitoring_scheduler.stop()
    _monitoring_scheduler = None
    app.state.monitoring_scheduler_started = False


class BulkDeleteRequest(BaseModel):
    ingest_ids: list[str]


class ExternalSchedulerHeartbeatRequest(BaseModel):
    job_name: str
    status: str = "ok"
    monitor_id: str | None = None
    message: str | None = None


class NewsBulkDeleteRequest(BaseModel):
    ids: list[int]


class NewsTriggerAnalysisRequest(BaseModel):
    monitor_id: str
    keyword: str | None = None
    window_days: int = 7
    news_hours: int = 72
    horizon: str = "24h"
    publish: bool = False


@app.get("/")
def index(page: str | None = None) -> HTMLResponse:
    # `/?page=topic` shows the original report-analysis dashboard.
    if page == "news":
        return HTMLResponse(
            """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>OpenClaw 新闻动态</title>
  <style>
    :root {
      --bg: #f7f8fb; --surface: #ffffff; --surface-2: #f1f3f7; --text: #1f2937;
      --muted: #6b7280; --line: #d8dee8; --brand: #0b4fa3; --link: #164b91; --header: #0a2f66; --header-text: #ffffff;
    }
    body.dark {
      --bg: #0f1218; --surface: #171c25; --surface-2: #202735; --text: #e6edf7;
      --muted: #9fb0c9; --line: #2c3444; --brand: #66a3ff; --link: #8eb8ff; --header: #101624; --header-text: #f3f6fd;
    }
    * { box-sizing: border-box; }
    body { margin:0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; color:var(--text); background:var(--bg); }
    .topbar { background:var(--header); color:var(--header-text); border-bottom: 1px solid rgba(255,255,255,.15); }
    .wrap { width: min(1200px, 100% - 28px); margin: 0 auto; }
    .topbar-inner { display:flex; align-items:center; justify-content:space-between; padding:12px 0; }
    .logo { font-size:20px; font-weight:700; letter-spacing:.5px; }
    .top-actions { display:flex; gap:8px; }
    .top-actions button { border:1px solid rgba(255,255,255,.35); background:rgba(255,255,255,.08); color:var(--header-text); padding:7px 12px; border-radius:12px; cursor:pointer; font-size:14px; }
    .nav { background:var(--surface); border-bottom:1px solid var(--line); margin-bottom:14px; }
    .nav ul { list-style:none; margin:0; padding:0; display:flex; gap:18px; overflow-x:auto; white-space:nowrap; }
    .nav li, .nav a { padding:12px 0; border-bottom:2px solid transparent; cursor:pointer; color:inherit; display:inline-block; text-decoration:none; }
    .nav li.active { border-color:var(--brand); color:var(--brand); font-weight:600; }
    .page { display:grid; grid-template-columns: 380px 1fr; gap:18px; padding-bottom:20px; }
    .left, .right { background:var(--surface); border:1px solid var(--line); border-radius:14px; }
    .panel-title { margin:0; font-size:18px; border-bottom:1px solid var(--line); padding:12px 14px; background:var(--surface-2); }
    .toolbar { display:flex; gap:8px; padding:10px 14px; border-bottom:1px solid var(--line); }
    .toolbar input, .toolbar button { border:1px solid var(--line); background:var(--surface); color:var(--text); padding:7px 10px; border-radius:12px; }
    .toolbar button.danger { border-color:#b42318; color:#b42318; background:transparent; }
    #news-list { list-style:none; margin:0; padding:0; max-height: calc(100vh - 245px); overflow:auto; }
    .pager { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:8px 14px 12px; border-top:1px solid var(--line); }
    .pager-meta { color:var(--muted); font-size:12px; }
    .pager-actions { display:flex; gap:8px; }
    .pager-actions button { border:1px solid var(--line); background:var(--surface); color:var(--text); padding:6px 10px; border-radius:10px; cursor:pointer; font-size:12px; }
    .pager-actions button:disabled { opacity:.45; cursor:not-allowed; }
    .news-item { padding:12px 14px; border-bottom:1px dashed var(--line); cursor:pointer; display:grid; grid-template-columns:22px 1fr; gap:8px; align-items:start; }
    .news-item:hover { background:var(--surface-2); }
    .news-item.active { border-left:3px solid var(--brand); background:var(--surface-2); }
    .news-title { font-size:15px; line-height:1.45; margin-bottom:4px; }
    .news-meta { color:var(--muted); font-size:12px; }
    .detail-wrap { padding:16px 18px 28px; line-height:1.75; }
    .detail-wrap h2 { margin:.2em 0 .6em; color:var(--brand); }
    .muted { color:var(--muted); }
    a { color:var(--link); text-decoration:none; }
    a:hover { text-decoration:underline; }
    .empty { padding:14px; color:var(--muted); }
  </style>
</head>
<body>
  <div class="topbar"><div class="wrap topbar-inner"><div class="logo">OpenClaw市场趋势自动化分析平台</div><div class="top-actions"><button onclick="toggleDarkMode()">暗色模式</button><button onclick="location.href='/docs'">接口文档</button></div></div></div>
  <div class="nav"><div class="wrap"><ul id="category-nav"><li><a href="/">门户首页</a></li><li class="active"><a href="/?page=news">新闻动态</a></li><li><a href="/price-trend">价格趋势</a></li><li><a href="/topic-analysis">专题分析</a></li><li><a href="/keyword-tracking">监测参数</a></li></ul></div></div>
  <div class="wrap">
    <div class="page">
      <div class="left">
        <h2 class="panel-title">新闻库条目</h2>
        <div class="toolbar">
          <input id="keyword-search" placeholder="输入关键词筛选" />
          <button id="refresh-btn">刷新</button>
          <button id="delete-btn" class="danger">删除选中</button>
        </div>
        <ul id="news-list"></ul>
        <div class="pager">
          <div id="news-page-meta" class="pager-meta">-</div>
          <div class="pager-actions">
            <button id="news-prev-btn" type="button">上一页</button>
            <button id="news-next-btn" type="button">下一页</button>
          </div>
        </div>
      </div>
      <div class="right">
        <h2 class="panel-title">新闻详情</h2>
        <div id="news-detail" class="detail-wrap muted">请先从左侧选择一条新闻。</div>
      </div>
    </div>
  </div>
  <script>
    let newsCache = [];
    let activeId = null;
    let selectedIds = new Set();
    let newsPage = 1;
    const NEWS_PAGE_SIZE = 10;
    function toggleDarkMode() { document.body.classList.toggle('dark'); localStorage.setItem('oc_dark', document.body.classList.contains('dark') ? '1' : '0'); }
    function setupDarkMode() { if (localStorage.getItem('oc_dark') === '1') document.body.classList.add('dark'); }
    function escapeHtml(text) { return String(text ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('\"','&quot;').replaceAll(\"'\",'&#039;'); }
    function filteredNews() {
      const kw = document.getElementById('keyword-search').value.trim().toLowerCase();
      if (!kw) return newsCache;
      return newsCache.filter((n) => String(n.keyword || '').toLowerCase().includes(kw) || String(n.title || '').toLowerCase().includes(kw) || String(n.summary || '').toLowerCase().includes(kw));
    }
    function getNewsPageSlice(arr) {
      const total = arr.length;
      const totalPages = Math.max(1, Math.ceil(total / NEWS_PAGE_SIZE));
      newsPage = Math.max(1, Math.min(newsPage, totalPages));
      const start = (newsPage - 1) * NEWS_PAGE_SIZE;
      return {
        rows: arr.slice(start, start + NEWS_PAGE_SIZE),
        total,
        totalPages,
        start,
      };
    }
    function renderNewsPager(total, totalPages, start) {
      const meta = document.getElementById('news-page-meta');
      const prevBtn = document.getElementById('news-prev-btn');
      const nextBtn = document.getElementById('news-next-btn');
      if (!total) {
        meta.textContent = '第 0 条，共 0 条';
        prevBtn.disabled = true;
        nextBtn.disabled = true;
        return;
      }
      const from = start + 1;
      const to = Math.min(start + NEWS_PAGE_SIZE, total);
      meta.textContent = `第 ${newsPage}/${totalPages} 页 · 显示 ${from}-${to} / ${total}`;
      prevBtn.disabled = newsPage <= 1;
      nextBtn.disabled = newsPage >= totalPages;
    }
    function renderList(arr) {
      const list = document.getElementById('news-list');
      list.innerHTML = '';
      if (!arr.length) { list.innerHTML = '<li class="empty">暂无新闻数据。</li>'; renderNewsPager(0, 1, 0); return; }
      const page = getNewsPageSlice(arr);
      for (const n of page.rows) {
        const li = document.createElement('li');
        li.className = 'news-item' + (activeId === n.id ? ' active' : '');
        li.innerHTML = `<input type="checkbox" class="row-check" data-id="${n.id}" ${selectedIds.has(n.id) ? 'checked' : ''} />
          <div>
            <div class="news-title">${escapeHtml(n.title || '未命名新闻')}</div>
            <div class="news-meta">关键词：${escapeHtml(n.keyword || '-')}</div>
            <div class="news-meta">时间：${escapeHtml(n.published_at || n.created_at || '-')}</div>
          </div>`;
        li.onclick = (e) => { if (e.target && e.target.classList.contains('row-check')) return; activeId = n.id; renderList(filteredNews()); renderDetail(n); };
        const ck = li.querySelector('.row-check');
        ck?.addEventListener('click', (e) => e.stopPropagation());
        ck?.addEventListener('change', (e) => {
          const id = Number(e.target.getAttribute('data-id'));
          if (!id) return;
          if (e.target.checked) selectedIds.add(id); else selectedIds.delete(id);
        });
        list.appendChild(li);
      }
      renderNewsPager(page.total, page.totalPages, page.start);
    }
    function renderDetail(n) {
      const box = document.getElementById('news-detail');
      box.innerHTML = `<h2>${escapeHtml(n.title || '未命名新闻')}</h2>
        <p><strong>关键词：</strong>${escapeHtml(n.keyword || '-')}</p>
        <p><strong>来源：</strong>${escapeHtml(n.source_name || '-')}</p>
        <p><strong>发布时间：</strong>${escapeHtml(n.published_at || n.created_at || '-')}</p>
        <p><strong>新闻概述：</strong></p>
        <p>${escapeHtml(n.summary || '-')}</p>
        <p><strong>原文链接：</strong><a href="${escapeHtml(n.source_url || '#')}" target="_blank" rel="noreferrer">直达原文</a></p>`;
    }
    async function loadNews() {
      const res = await fetch('/api/v1/public/news/library?limit=300');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      newsCache = Array.isArray(data) ? data : [];
      const arr = filteredNews();
      newsPage = 1;
      renderList(arr);
      if (!activeId && arr.length) { activeId = arr[0].id; renderList(arr); renderDetail(arr[0]); }
    }
    async function deleteSelectedNews() {
      if (!selectedIds.size) { alert('请先勾选需要删除的新闻。'); return; }
      if (!confirm(`确认删除选中的 ${selectedIds.size} 条新闻吗？`)) return;
      const res = await fetch('/api/v1/public/news/library/bulk-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: Array.from(selectedIds) }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      selectedIds.clear();
      activeId = null;
      document.getElementById('news-detail').innerHTML = '<div class="muted">删除成功，请从左侧重新选择新闻。</div>';
      await loadNews();
    }
    document.getElementById('keyword-search').addEventListener('input', () => { newsPage = 1; renderList(filteredNews()); });
    document.getElementById('news-prev-btn').addEventListener('click', () => { newsPage -= 1; renderList(filteredNews()); });
    document.getElementById('news-next-btn').addEventListener('click', () => { newsPage += 1; renderList(filteredNews()); });
    document.getElementById('news-list').addEventListener('wheel', (e) => {
      const list = e.currentTarget;
      if (e.deltaY > 0 && list.scrollTop + list.clientHeight >= list.scrollHeight - 2) {
        const arr = filteredNews();
        const maxPage = Math.max(1, Math.ceil(arr.length / NEWS_PAGE_SIZE));
        if (newsPage < maxPage) {
          e.preventDefault();
          newsPage += 1;
          renderList(arr);
          list.scrollTop = 0;
        }
      } else if (e.deltaY < 0 && list.scrollTop <= 1) {
        if (newsPage > 1) {
          e.preventDefault();
          newsPage -= 1;
          renderList(filteredNews());
          list.scrollTop = list.scrollHeight;
        }
      }
    }, { passive: false });
    document.getElementById('refresh-btn').addEventListener('click', async () => { try { await loadNews(); } catch (e) { document.getElementById('news-list').innerHTML = `<li class="empty">加载失败：${escapeHtml(e?.message || '未知错误')}</li>`; }});
    document.getElementById('delete-btn').addEventListener('click', async () => {
      try { await deleteSelectedNews(); } catch (e) { alert(`删除失败：${e?.message || '未知错误'}`); }
    });
    setupDarkMode();
    loadNews().catch((e) => { document.getElementById('news-list').innerHTML = `<li class="empty">加载失败：${escapeHtml(e?.message || '未知错误')}</li>`; });
  </script>
</body>
</html>
"""
        )
    if page != "topic":
        return HTMLResponse(
            """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>OpenClaw市场趋势自动化分析平台</title>
  <style>
    :root {
      --bg: #f7f8fb;
      --surface: #ffffff;
      --surface-2: #f1f3f7;
      --text: #1f2937;
      --muted: #6b7280;
      --line: #d8dee8;
      --brand: #0b4fa3;
      --link: #164b91;
      --header: #0a2f66;
      --header-text: #ffffff;
    }
    body.dark {
      --bg: #0f1218;
      --surface: #171c25;
      --surface-2: #202735;
      --text: #e6edf7;
      --muted: #9fb0c9;
      --line: #2c3444;
      --brand: #66a3ff;
      --link: #8eb8ff;
      --header: #101624;
      --header-text: #f3f6fd;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background: var(--bg);
    }
    .topbar {
      background: var(--header);
      color: var(--header-text);
      border-bottom: 1px solid rgba(255,255,255,0.15);
    }
    .wrap { width: min(1200px, 100% - 28px); margin: 0 auto; }
    .topbar-inner {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 0;
    }
    .logo { font-size: 20px; font-weight: 700; letter-spacing: .5px; }
    .top-actions { display: flex; gap: 10px; align-items: center; }
    .top-actions button {
      border: 1px solid rgba(255,255,255,.35);
      background: rgba(255,255,255,.08);
      color: var(--header-text);
      padding: 7px 12px;
      border-radius: 12px;
      cursor: pointer;
      font-size: 14px;
    }

    .nav {
      background: var(--surface);
      border-bottom: 1px solid var(--line);
      margin-bottom: 14px;
    }
    .nav ul {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      gap: 18px;
      overflow-x: auto;
      white-space: nowrap;
    }
    .nav li, .nav a {
      padding: 12px 0;
      border-bottom: 2px solid transparent;
      cursor: pointer;
      color: inherit;
      display: inline-block;
      text-decoration: none;
    }
    .nav li.active { border-color: var(--brand); color: var(--brand); font-weight: 600; }

    .portal-hero { padding: 22px 0 14px; }
    .portal-hero h1 { margin: 0 0 8px; font-size: 22px; color: var(--brand); }
    .portal-hero p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.6; }

    .cards {
      display: flex;
      flex-direction: column;
      gap: 14px;
      align-items: stretch;
      padding-bottom: 26px;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 16px 16px 14px;
    }
    .card-title {
      margin: 0 0 10px;
      font-size: 16px;
      color: var(--brand);
      font-weight: 700;
    }
    textarea {
      width: 100%;
      min-height: 110px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: var(--surface-2);
      color: var(--text);
      padding: 10px 12px;
      outline: none;
      resize: vertical;
      font-family: inherit;
      line-height: 1.6;
    }
    .card-actions { display: flex; gap: 10px; margin-top: 10px; }
    .btn {
      border: 1px solid var(--line);
      background: var(--surface-2);
      color: var(--text);
      padding: 10px 14px;
      border-radius: 14px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 600;
    }
    .btn.primary {
      border-color: rgba(11,79,163,0.35);
      background: rgba(11,79,163,0.10);
      color: var(--brand);
    }
    .muted { color: var(--muted); }

    .chat-messages {
      height: 260px;
      overflow: auto;
      padding: 10px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      background: var(--surface);
      border: 1px dashed var(--line);
      border-radius: 14px;
    }
    .chat-row {
      display: flex;
      width: 100%;
    }
    .chat-row.user { justify-content: flex-end; }
    .chat-row.assistant { justify-content: flex-start; }
    .bubble {
      max-width: 86%;
      padding: 10px 12px;
      border-radius: 14px;
      border: 1px solid var(--line);
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.65;
    }
    .bubble.user {
      background: rgba(11,79,163,0.12);
      border-color: rgba(11,79,163,0.35);
    }
    .bubble.assistant {
      background: var(--surface-2);
    }
    .chat-input-row {
      display: flex;
      gap: 10px;
      margin-top: 10px;
      align-items: flex-end;
    }
    .chat-input-row textarea {
      min-height: 56px;
      max-height: 140px;
    }
    .send-btn[disabled] {
      opacity: 0.65;
      cursor: not-allowed;
    }

    .btn.danger {
      border-color: #b42318;
      color: #b42318;
      background: transparent;
    }

    .chat-session-bar {
      display: flex;
      gap: 10px;
      align-items: center;
      margin-top: 12px;
      padding: 10px 12px;
      border: 1px dashed var(--line);
      border-radius: 14px;
      background: var(--surface);
    }

    #chat-session-select {
      flex: 1;
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--text);
      padding: 10px 12px;
      outline: none;
      border-radius: 12px;
      min-width: 0;
    }

    .chat-empty {
      color: var(--muted);
      padding: 10px 12px;
    }

    #status-list { list-style: none; padding: 0; margin: 10px 0 0; }
    .status-item {
      padding: 0;
      border: 1px dashed var(--line);
      border-radius: 14px;
      margin-bottom: 10px;
      background: var(--surface);
      overflow: hidden;
    }
    .status-item-link {
      display: block;
      padding: 10px 12px;
      color: inherit;
      text-decoration: none;
    }
    .status-item-link:hover .status-item-title { color: var(--brand); }
    .status-item-link:focus-visible {
      outline: 2px solid var(--brand);
      outline-offset: -2px;
    }
    .status-item-body { padding: 10px 12px; }
    .status-item-title { font-weight: 650; margin-bottom: 4px; font-size: 14px; }
    .status-item-meta { color: var(--muted); font-size: 12px; }

    .portal-footer {
      padding: 18px 0 36px;
      color: var(--muted);
      font-size: 13px;
      text-align: center;
    }
    .portal-footer a { color: var(--link); text-decoration: none; }
    .portal-footer a:hover { text-decoration: underline; }

    .modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.45);
      display: none;
      align-items: center;
      justify-content: center;
      padding: 18px;
      z-index: 1000;
    }
    .modal {
      width: min(560px, 100%);
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 16px 16px 14px;
      box-shadow: 0 18px 40px rgba(0,0,0,0.35);
    }
    .modal-title { font-weight: 800; color: var(--brand); margin: 0 0 8px; }
    .modal-body { color: var(--text); white-space: pre-wrap; line-height: 1.6; }
    .modal-actions { display: flex; justify-content: flex-end; margin-top: 14px; }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="wrap topbar-inner">
      <div class="logo">OpenClaw市场趋势自动化分析平台</div>
      <div class="top-actions">
        <button onclick="toggleDarkMode()">暗色模式</button>
        <button onclick="location.href='/docs'">接口文档</button>
      </div>
    </div>
  </div>

  <div class="nav">
    <div class="wrap">
      <ul id="category-nav">
        <li class="active"><a href="/">门户首页</a></li>
        <li><a href="/?page=news">新闻动态</a></li>
        <li><a href="/price-trend">价格趋势</a></li>
        <li><a href="/topic-analysis">专题分析</a></li>
        <li><a href="/keyword-tracking">监测参数</a></li>
      </ul>
    </div>
  </div>

  <div class="wrap">
    <div class="portal-hero">
      <h1>OpenClaw市场趋势自动化分析平台</h1>
      <p>选择一个模块进入页面；也可以在下方向 OpenClaw 发送消息。</p>
    </div>

    <div class="cards">
      <div class="card chat-card">
        <div class="card-title">OpenClaw 对话</div>
        <div class="chat-session-bar">
          <select id="chat-session-select"></select>
          <button class="btn" id="chat-new-session-btn" type="button">新建会话</button>
          <button class="btn danger" id="chat-delete-session-btn" type="button">删除</button>
          <button class="btn danger" id="chat-clear-cache-btn" type="button">清空缓存</button>
        </div>
        <div id="chat-messages" class="chat-messages"></div>
        <div class="chat-input-row">
          <textarea id="openclaw-chat-input" placeholder="输入你希望 OpenClaw 处理的自由文本（例如：分析某关键词、时间范围或直接提问）。"></textarea>
          <button class="btn primary send-btn" id="chat-send-btn">发送</button>
        </div>
      </div>

      <div class="card status-card">
        <div class="card-title">OpenClaw 工作情况</div>
        <div class="muted" id="status-summary">加载中...</div>
        <div class="muted" id="work-overview-hint" style="font-size:13px;margin-top:6px;line-height:1.5;">
          价格与新闻进度建议每 30 分钟对照一次；本卡片每 30 分钟自动刷新（仍可在下方手动刷新页面）。
        </div>
        <ul id="status-list"></ul>
      </div>
    </div>
  </div>

  <div class="portal-footer">
    <div>作者：maniac1um</div>
    <div style="margin-top:6px;"><a href="mailto:maniac1um@163.com">联系作者</a></div>
  </div>

  <script>
    function toggleDarkMode() {
      document.body.classList.toggle('dark');
      localStorage.setItem('oc_dark', document.body.classList.contains('dark') ? '1' : '0');
    }
    function setupDarkMode() {
      if (localStorage.getItem('oc_dark') === '1') {
        document.body.classList.add('dark');
      }
    }
    function appendSectionHeading(list, title, metaText) {
      const li = document.createElement('li');
      li.className = 'status-item';
      const body = document.createElement('div');
      body.className = 'status-item-body';
      const t = document.createElement('div');
      t.className = 'status-item-title';
      t.style.fontWeight = '800';
      t.style.color = 'var(--brand)';
      t.textContent = title;
      const m = document.createElement('div');
      m.className = 'status-item-meta';
      m.textContent = metaText;
      body.appendChild(t);
      body.appendChild(m);
      li.appendChild(body);
      list.appendChild(li);
    }
    function appendStatusMetaItem(list, title, lines) {
      const li = document.createElement('li');
      li.className = 'status-item';
      const body = document.createElement('div');
      body.className = 'status-item-body';
      const t = document.createElement('div');
      t.className = 'status-item-title';
      t.textContent = title;
      body.appendChild(t);
      for (const line of (lines || [])) {
        const m = document.createElement('div');
        m.className = 'status-item-meta';
        m.textContent = line;
        body.appendChild(m);
      }
      li.appendChild(body);
      list.appendChild(li);
    }

    async function loadOpenClawWorkOverview() {
      const summary = document.getElementById('status-summary');
      const list = document.getElementById('status-list');
      summary.textContent = '加载中...';
      list.innerHTML = '';
      try {
        const res = await fetch('/api/v1/public/portal/openclaw-work-overview');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const o = await res.json();
        const rc = o.reports?.published_count ?? 0;
        const pc = o.price_monitoring?.observation_count ?? 0;
        const nc = o.news_library?.item_count ?? 0;
        const jc = o.external_cron?.job_count ?? 0;
        summary.textContent = `报告 ${rc} 条 · 价格观测 ${pc} 条 · 新闻库 ${nc} 条 · 外部定时 ${jc} 个`;

        const rep = o.reports || {};
        if (rep.error) {
          appendSectionHeading(list, '报告发布', '读取失败：' + rep.error);
        } else if (!rep.available) {
          appendSectionHeading(list, '报告发布', '未配置主库 OPENCLAW_DATABASE_URL。');
        } else {
          appendSectionHeading(
            list,
            '报告发布',
            '已发布 ' + rep.published_count + ' 条 · 最近更新：' + (rep.last_generated_at || '—'),
          );
          const top = rep.recent || [];
          if (!top.length) {
            const li = document.createElement('li');
            li.className = 'status-item';
            const body = document.createElement('div');
            body.className = 'status-item-body';
            const m = document.createElement('div');
            m.className = 'status-item-meta';
            m.textContent = '暂无报告，等待 OpenClaw 入站。';
            body.appendChild(m);
            li.appendChild(body);
            list.appendChild(li);
          } else {
            for (const r of top) {
              const li = document.createElement('li');
              li.className = 'status-item';
              const title = r.title || '未命名报告';
              const meta = r.generated_at || '-';
              const id = r.ingest_id;
              if (id) {
                const a = document.createElement('a');
                a.className = 'status-item-link';
                a.href = '/?page=news&report=' + encodeURIComponent(id);
                a.setAttribute('title', '在新闻动态中打开此报告');
                const t = document.createElement('div');
                t.className = 'status-item-title';
                t.textContent = title;
                const m = document.createElement('div');
                m.className = 'status-item-meta';
                m.textContent = '生成时间：' + meta;
                a.appendChild(t);
                a.appendChild(m);
                li.appendChild(a);
              } else {
                const body = document.createElement('div');
                body.className = 'status-item-body';
                const t0 = document.createElement('div');
                t0.className = 'status-item-title';
                t0.textContent = title;
                const m0 = document.createElement('div');
                m0.className = 'status-item-meta';
                m0.textContent = '生成时间：' + meta;
                body.appendChild(t0);
                body.appendChild(m0);
                li.appendChild(body);
              }
              list.appendChild(li);
            }
          }
        }

        const pr = o.price_monitoring || {};
        if (pr.error) {
          appendSectionHeading(list, '价格趋势监测', '读取失败：' + pr.error);
        } else if (!pr.available) {
          appendSectionHeading(list, '价格趋势监测', '未配置监测库 OPENCLAW_MONITORING_DATABASE_URL。');
        } else {
          appendSectionHeading(
            list,
            '价格趋势监测',
            '监测任务 ' +
              pr.monitor_count +
              ' 个 · 累计观测 ' +
              pr.observation_count +
              ' 条 · 最近采样：' +
              (pr.last_captured_at || '—'),
          );
          const recentMonitors = Array.isArray(pr.recent) ? pr.recent : [];
          for (const m of recentMonitors.slice(0, 6)) {
            appendStatusMetaItem(
              list,
              (m.keyword || '未命名关键词') + '（' + (m.monitor_id || '-').slice(0, 8) + '）',
              [
                '观测数：' + (m.observation_count ?? 0),
                '最近采样：' + (m.last_captured_at || '—'),
              ],
            );
          }
        }

        const nw = o.news_library || {};
        if (nw.error) {
          appendSectionHeading(list, '新闻动态监测（新闻库）', '读取失败：' + nw.error);
        } else if (!nw.available) {
          appendSectionHeading(list, '新闻动态监测（新闻库）', '未配置新闻库 OPENCLAW_NEWS_DATABASE_URL。');
        } else {
          appendSectionHeading(
            list,
            '新闻动态监测（新闻库）',
            '库内 ' + nw.item_count + ' 条 · 最近入库：' + (nw.last_created_at || '—'),
          );
          const keywordRows = Array.isArray(nw.recent_keywords) ? nw.recent_keywords : [];
          for (const row of keywordRows.slice(0, 6)) {
            appendStatusMetaItem(
              list,
              row.keyword || '未命名关键词',
              [
                '条目数：' + (row.item_count ?? 0),
                '最近事件时间：' + (row.last_event_at || row.last_created_at || '—'),
              ],
            );
          }
        }

        const ext = o.external_cron || {};
        const jobs = Array.isArray(ext.jobs) ? ext.jobs : [];
        appendSectionHeading(
          list,
          '外部定时任务（cron / OpenClaw cron）',
          '已上报 ' + jobs.length + ' 个 · 通过 external-heartbeat 写入',
        );
        if (!jobs.length) {
          const empty = document.createElement('li');
          empty.className = 'status-item';
          const body = document.createElement('div');
          body.className = 'status-item-body';
          const m = document.createElement('div');
          m.className = 'status-item-meta';
          m.textContent = '暂无心跳记录。可 POST /api/v1/openclaw/monitoring/external-heartbeat 上报。';
          body.appendChild(m);
          empty.appendChild(body);
          list.appendChild(empty);
        } else {
          for (const job of jobs.slice(0, 12)) {
            appendStatusMetaItem(
              list,
              (job.job_name || '-') + '（' + (job.status || 'unknown') + '）',
              [
                'monitor_id: ' + (job.monitor_id || '-'),
                'last_seen_at: ' + (job.last_seen_at || '-'),
                'message: ' + (job.message || '-'),
              ],
            );
          }
        }
      } catch (err) {
        summary.textContent = '加载失败';
        const li = document.createElement('li');
        li.className = 'status-item';
        li.innerHTML =
          '<div class="status-item-body"><div class="status-item-title">无法获取工作情况</div><div class="status-item-meta">' +
          (err?.message || '未知错误') +
          '</div></div>';
        list.appendChild(li);
      }
    }

    const chatMessages = document.getElementById('chat-messages');
    const chatInput = document.getElementById('openclaw-chat-input');
    const chatSendBtn = document.getElementById('chat-send-btn');

    const chatSessionSelect = document.getElementById('chat-session-select');
    const chatNewSessionBtn = document.getElementById('chat-new-session-btn');
    const chatDeleteSessionBtn = document.getElementById('chat-delete-session-btn');
    const chatClearCacheBtn = document.getElementById('chat-clear-cache-btn');

    const CHAT_STORAGE_KEY = 'oc_portal_chat_v1';
    const MAX_CHAT_SESSIONS = 20;
    const MAX_MESSAGES_PER_SESSION = 200;

    let chatWs = null;
    // Whether the backend is currently streaming a reply for SOME session.
    let isStreaming = false;
    let serverBusySessionKey = null;

    // Multi-session local UI state: sessionKey -> messages
    // Note: backend WebSocket connection is still sequential per browser page.
    let sessions = {};
    let sessionOrder = [];

    let activeSessionKey = null;
    let activeAssistantBubble = null;
    let nextSessionNum = 1;

    function _toSafeText(v) {
      if (typeof v !== 'string') return '';
      return v.slice(0, 4000);
    }

    function _normalizeMessages(arr) {
      if (!Array.isArray(arr)) return [];
      const out = [];
      for (const item of arr) {
        if (!item || (item.side !== 'user' && item.side !== 'assistant')) continue;
        const text = _toSafeText(item.text || '');
        out.push({ side: item.side, text });
      }
      return out.slice(-MAX_MESSAGES_PER_SESSION);
    }

    function _normalizeSession(raw, fallbackId) {
      const id = _toSafeText(raw?.id || fallbackId || '').trim() || genSessionKey();
      const title = _toSafeText(raw?.title || id).trim() || id;
      const messages = _normalizeMessages(raw?.messages);
      const idxRaw = Number(raw?.assistantIndex);
      const assistantIndex = Number.isInteger(idxRaw) && idxRaw >= 0 && idxRaw < messages.length ? idxRaw : null;
      return { id, title, messages, assistantIndex, assistantBubbleEl: null };
    }

    function _trimSessionsInPlace() {
      const uniqOrder = [];
      const seen = new Set();
      for (const id of sessionOrder) {
        if (!sessions[id] || seen.has(id)) continue;
        seen.add(id);
        uniqOrder.push(id);
      }
      sessionOrder = uniqOrder.slice(0, MAX_CHAT_SESSIONS);
      const keep = new Set(sessionOrder);
      for (const id of Object.keys(sessions)) {
        if (!keep.has(id)) delete sessions[id];
      }
      for (const id of sessionOrder) {
        sessions[id].messages = _normalizeMessages(sessions[id].messages);
        const idxRaw = Number(sessions[id].assistantIndex);
        sessions[id].assistantIndex = Number.isInteger(idxRaw) && idxRaw >= 0 && idxRaw < sessions[id].messages.length
          ? idxRaw
          : null;
      }
      if (!activeSessionKey || !sessions[activeSessionKey]) {
        activeSessionKey = sessionOrder[0] || null;
      }
    }

    function saveChatState() {
      try {
        _trimSessionsInPlace();
        const payload = {
          version: 1,
          nextSessionNum,
          activeSessionKey,
          sessionOrder,
          sessions: {},
        };
        for (const id of sessionOrder) {
          const s = sessions[id];
          payload.sessions[id] = {
            id: s.id,
            title: s.title,
            messages: s.messages,
            assistantIndex: s.assistantIndex,
          };
        }
        localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(payload));
      } catch (e) {
        // ignore quota/security/localStorage errors
      }
    }

    function loadChatState() {
      try {
        const raw = localStorage.getItem(CHAT_STORAGE_KEY);
        if (!raw) return false;
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object') return false;
        const parsedSessions = parsed.sessions || {};
        const parsedOrder = Array.isArray(parsed.sessionOrder) ? parsed.sessionOrder : [];
        const rebuilt = {};
        const rebuiltOrder = [];
        for (const id of parsedOrder) {
          if (typeof id !== 'string') continue;
          const s = _normalizeSession(parsedSessions[id], id);
          rebuilt[s.id] = s;
          rebuiltOrder.push(s.id);
          if (rebuiltOrder.length >= MAX_CHAT_SESSIONS) break;
        }
        if (!rebuiltOrder.length) return false;
        sessions = rebuilt;
        sessionOrder = rebuiltOrder;
        activeSessionKey = typeof parsed.activeSessionKey === 'string' && rebuilt[parsed.activeSessionKey]
          ? parsed.activeSessionKey
          : rebuiltOrder[0];
        const n = Number(parsed.nextSessionNum);
        nextSessionNum = Number.isInteger(n) && n > 0 ? n : (rebuiltOrder.length + 1);
        _trimSessionsInPlace();
        return true;
      } catch (e) {
        return false;
      }
    }

    function addChatRow(side, text) {
      const row = document.createElement('div');
      row.className = `chat-row ${side}`;
      const bubble = document.createElement('div');
      bubble.className = `bubble ${side}`;
      bubble.textContent = text;
      row.appendChild(bubble);
      chatMessages.appendChild(row);
      chatMessages.scrollTop = chatMessages.scrollHeight;
      return bubble;
    }

    function genSessionKey() {
      if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
      return 'session-' + Date.now() + '-' + Math.random().toString(16).slice(2);
    }

    function rebuildSessionSelect() {
      chatSessionSelect.innerHTML = '';
      for (const id of sessionOrder) {
        const opt = document.createElement('option');
        opt.value = id;
        opt.textContent = sessions[id]?.title || id;
        chatSessionSelect.appendChild(opt);
      }
      if (activeSessionKey && sessions[activeSessionKey]) {
        chatSessionSelect.value = activeSessionKey;
      }
    }

    function renderActiveChat() {
      chatMessages.innerHTML = '';
      activeAssistantBubble = null;

      // Clear cached DOM refs in all sessions.
      for (const s of Object.values(sessions)) {
        s.assistantBubbleEl = null;
      }

      const session = sessions[activeSessionKey];
      if (!session) return;

      if (!session.messages.length) {
        const empty = document.createElement('div');
        empty.className = 'chat-empty';
        empty.textContent = '暂无对话消息：点击“新建会话”或发送第一句。';
        chatMessages.appendChild(empty);
        return;
      }

      for (let i = 0; i < session.messages.length; i++) {
        const msg = session.messages[i];
        const bubble = addChatRow(msg.side, msg.text);
        if (msg.side === 'assistant' && session.assistantIndex === i) {
          session.assistantBubbleEl = bubble;
          activeAssistantBubble = bubble;
        }
      }
    }

    function createSession() {
      const id = genSessionKey();
      const title = `会话 ${nextSessionNum++}`;
      sessions[id] = {
        id,
        title,
        messages: [],
        assistantIndex: null,
        assistantBubbleEl: null,
      };
      sessionOrder.unshift(id);
      activeSessionKey = id;
      _trimSessionsInPlace();
      rebuildSessionSelect();
      renderActiveChat();
      saveChatState();
      return id;
    }

    function deleteActiveSession() {
      if (!activeSessionKey) return;
      if (isStreaming) {
        alert('当前仍在生成中，请等待完成后再删除会话。');
        return;
      }
      if (!confirm('确认删除当前会话吗？')) return;

      const id = activeSessionKey;
      delete sessions[id];
      sessionOrder = sessionOrder.filter((x) => x !== id);

      if (!sessionOrder.length) {
        sessions = {};
        sessionOrder = [];
        activeSessionKey = null;
        createSession();
        return;
      }

      activeSessionKey = sessionOrder[0];
      rebuildSessionSelect();
      renderActiveChat();
      saveChatState();
    }

    function clearAllChatCache() {
      if (isStreaming) {
        alert('当前仍在生成中，请等待完成后再清空缓存。');
        return;
      }
      if (!confirm('确认清空所有会话缓存吗？此操作不可恢复。')) return;
      sessions = {};
      sessionOrder = [];
      activeSessionKey = null;
      nextSessionNum = 1;
      try { localStorage.removeItem(CHAT_STORAGE_KEY); } catch (e) {}
      createSession();
    }

    function connectChatWs() {
      const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = wsProto + '//' + location.host + '/api/v1/chat/ws';
      chatWs = new WebSocket(wsUrl);

      chatWs.onopen = () => {
        // Keep connected for this page.
      };

      chatWs.onmessage = (event) => {
        let data = null;
        try {
          data = JSON.parse(event.data);
        } catch (e) {
          return;
        }
        if (!data || !data.sessionKey) return;
        const sessionKey = data.sessionKey;
        const session = sessions[sessionKey];
        if (!session) {
          // If the session was deleted while streaming, we still must unfreeze UI.
          if (sessionKey === serverBusySessionKey) {
            isStreaming = false;
            serverBusySessionKey = null;
            chatSendBtn.disabled = false;
            chatInput.disabled = false;
            chatInput.focus();
          }
          return;
        }

        if (data.type === 'assistant_delta') {
          const text = data.text ?? '';
          if (session.assistantIndex === null) return;
          session.messages[session.assistantIndex].text = text;
          if (session.assistantBubbleEl) session.assistantBubbleEl.textContent = text;
          saveChatState();
          if (data.done && sessionKey === serverBusySessionKey) {
            isStreaming = false;
            serverBusySessionKey = null;
            chatSendBtn.disabled = false;
            chatInput.disabled = false;
            chatInput.focus();
            activeAssistantBubble = null;
          }
        } else if (data.type === 'assistant_error') {
          const errText = `回复失败：${data.error || '未知错误'}`;
          if (session.assistantIndex !== null) {
            session.messages[session.assistantIndex].text = errText;
          }
          if (session.assistantBubbleEl) session.assistantBubbleEl.textContent = errText;
          saveChatState();
          if (sessionKey === serverBusySessionKey) {
            isStreaming = false;
            serverBusySessionKey = null;
            chatSendBtn.disabled = false;
            chatInput.disabled = false;
            chatInput.focus();
            activeAssistantBubble = null;
          }
        }
      };

      chatWs.onerror = () => {
        // Non-fatal: the send button will fail if WS can't connect.
      };
    }

    chatSessionSelect.addEventListener('change', () => {
      activeSessionKey = chatSessionSelect.value;
      renderActiveChat();
      saveChatState();
      chatInput.focus();
    });

    chatNewSessionBtn.addEventListener('click', () => {
      createSession();
      chatInput.focus();
    });

    chatDeleteSessionBtn.addEventListener('click', () => {
      deleteActiveSession();
      chatInput.focus();
    });

    chatClearCacheBtn.addEventListener('click', () => {
      clearAllChatCache();
      chatInput.focus();
    });

    chatSendBtn.addEventListener('click', () => {
      const input = chatInput.value.trim();
      if (!input) return;
      if (!chatWs || chatWs.readyState !== WebSocket.OPEN) return;
      if (isStreaming) return;

      if (!activeSessionKey || !sessions[activeSessionKey]) {
        createSession();
      }

      isStreaming = true;
      serverBusySessionKey = activeSessionKey;
      chatSendBtn.disabled = true;
      chatInput.disabled = true;

      const sessionKey = activeSessionKey;
      const session = sessions[sessionKey];
      session.messages.push({ side: 'user', text: input });
      session.messages.push({ side: 'assistant', text: 'OpenClaw 正在生成中...' });
      session.messages = _normalizeMessages(session.messages);
      session.assistantIndex = session.messages.length - 1;

      renderActiveChat();
      saveChatState();

      chatWs.send(JSON.stringify({
        type: 'user_message',
        text: input,
        sessionKey: sessionKey,
      }));

      chatInput.value = '';
    });

    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatSendBtn.click();
      }
    });

    if (!loadChatState()) {
      createSession();
    } else {
      rebuildSessionSelect();
      renderActiveChat();
    }
    connectChatWs();

    setupDarkMode();
    loadOpenClawWorkOverview();
    setInterval(loadOpenClawWorkOverview, 30 * 60 * 1000);
  </script>
</body>
</html>
"""
        )

    return HTMLResponse(
        """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>OpenClaw市场趋势自动化分析平台</title>
  <style>
    :root {
      --bg: #f7f8fb;
      --surface: #ffffff;
      --surface-2: #f1f3f7;
      --text: #1f2937;
      --muted: #6b7280;
      --line: #d8dee8;
      --brand: #0b4fa3;
      --link: #164b91;
      --header: #0a2f66;
      --header-text: #ffffff;
    }
    body.dark {
      --bg: #0f1218;
      --surface: #171c25;
      --surface-2: #202735;
      --text: #e6edf7;
      --muted: #9fb0c9;
      --line: #2c3444;
      --brand: #66a3ff;
      --link: #8eb8ff;
      --header: #101624;
      --header-text: #f3f6fd;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background: var(--bg);
    }
    .topbar {
      background: var(--header);
      color: var(--header-text);
      border-bottom: 1px solid rgba(255,255,255,0.15);
    }
    .wrap { width: min(1200px, 100% - 28px); margin: 0 auto; }
    .topbar-inner {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 0;
    }
    .logo { font-size: 20px; font-weight: 700; letter-spacing: .5px; }
    .top-actions { display: flex; gap: 8px; }
    .top-actions button {
      border: 1px solid rgba(255,255,255,.35);
      background: rgba(255,255,255,.08);
      color: var(--header-text);
      padding: 7px 12px;
      border-radius: 12px;
      cursor: pointer;
      font-size: 14px;
    }
    .nav {
      background: var(--surface);
      border-bottom: 1px solid var(--line);
      margin-bottom: 14px;
    }
    .nav ul {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      gap: 18px;
      overflow-x: auto;
      white-space: nowrap;
    }
    .nav li, .nav a {
      padding: 12px 0;
      border-bottom: 2px solid transparent;
      cursor: pointer;
      color: inherit;
      display: inline-block;
    }
    .nav li.active { border-color: var(--brand); color: var(--brand); font-weight: 600; }
    .page {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 18px;
      padding-bottom: 20px;
    }
    .left, .right {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 14px;
    }
    .panel-title {
      margin: 0;
      font-size: 18px;
      border-bottom: 1px solid var(--line);
      padding: 12px 14px;
      background: var(--surface-2);
    }
    .toolbar {
      display: flex;
      gap: 8px;
      padding: 10px 14px;
      border-bottom: 1px solid var(--line);
    }
    .toolbar input {
      flex: 1;
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--text);
      padding: 7px 10px;
      outline: none;
      border-radius: 12px;
    }
    .toolbar button {
      border: 1px solid var(--line);
      background: var(--surface-2);
      color: var(--text);
      padding: 7px 10px;
      cursor: pointer;
      border-radius: 12px;
    }
    .toolbar button.danger {
      border-color: #b42318;
      color: #b42318;
      background: transparent;
    }
    #report-list {
      list-style: none;
      margin: 0;
      padding: 0;
      max-height: calc(100vh - 245px);
      overflow: auto;
    }
    .report-item {
      padding: 12px 14px;
      border-bottom: 1px dashed var(--line);
      cursor: pointer;
      background: var(--surface);
      display: grid;
      grid-template-columns: 22px 1fr;
      gap: 8px;
      align-items: start;
    }
    .report-item:hover { background: var(--surface-2); }
    .report-item.active { border-left: 3px solid var(--brand); background: var(--surface-2); }
    .report-title { font-size: 15px; line-height: 1.45; margin-bottom: 4px; }
    .report-meta { color: var(--muted); font-size: 12px; }
    .detail-wrap { padding: 16px 18px 28px; line-height: 1.75; }
    .detail-wrap h1, .detail-wrap h2, .detail-wrap h3 { line-height: 1.4; margin: 1.1em 0 .5em; color: var(--brand); }
    .detail-wrap p { margin: .6em 0; }
    .detail-wrap ul { padding-left: 20px; }
    .detail-wrap code {
      font-family: Consolas, "Courier New", monospace;
      font-size: 12px;
      background: var(--surface-2);
      border: 1px solid var(--line);
      padding: 1px 4px;
    }
    .detail-wrap pre {
      background: #0d1422;
      color: #dce7ff;
      padding: 12px;
      overflow: auto;
    }
    .muted { color: var(--muted); }
    a { color: var(--link); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .status-line { font-size: 13px; color: var(--muted); margin-top: 6px; }
    .empty { padding: 14px; color: var(--muted); }
    .footer-note {
      margin-top: 10px;
      color: var(--muted);
      font-size: 12px;
      padding: 0 2px;
    }
    @media (max-width: 920px) {
      .page { grid-template-columns: 1fr; }
      #report-list { max-height: 340px; }
    }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="wrap topbar-inner">
      <div class="logo">OpenClaw市场趋势自动化分析平台</div>
      <div class="top-actions">
        <button onclick="toggleDarkMode()">暗色模式</button>
        <button onclick="location.href='/docs'">接口文档</button>
      </div>
    </div>
  </div>
  <div class="nav">
    <div class="wrap">
      <ul id="category-nav">
        <li><a href="/">门户首页</a></li>
        <li><a href="/?page=news">新闻动态</a></li>
        <li><a href="/price-trend">价格趋势</a></li>
        <li class="active"><a href="/topic-analysis">专题分析</a></li>
        <li><a href="/keyword-tracking">监测参数</a></li>
      </ul>
    </div>
  </div>
  <div class="wrap">
    <div class="page">
      <div class="left">
        <h2 class="panel-title">报告栏目</h2>
        <div class="toolbar">
          <input id="keyword-search" placeholder="输入关键词筛选" />
          <button onclick="loadReports()">刷新</button>
          <button class="danger" onclick="deleteSelectedReports()">删除选中</button>
        </div>
        <div class="status-line" id="report-count" style="padding: 0 14px;">加载中...</div>
        <ul id="report-list"></ul>
      </div>
      <div class="right">
        <h2 class="panel-title">内容详情</h2>
        <div id="report-detail" class="detail-wrap muted">请先从左侧选择一个报告。</div>
      </div>
    </div>
    <div class="footer-note">注：详情内容支持 Markdown 渲染，适合直接展示分析结论。</div>
  </div>
  <script>
    let reportCache = [];
    let activeIngestId = null;
    let selectedIds = new Set();

    function getReportIdFromQuery() {
      return new URLSearchParams(window.location.search).get('report');
    }

    function escapeHtml(text) {
      return String(text ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
    }

    function toggleDarkMode() {
      document.body.classList.toggle('dark');
      localStorage.setItem('oc_dark', document.body.classList.contains('dark') ? '1' : '0');
    }

    function setupDarkMode() {
      if (localStorage.getItem('oc_dark') === '1') {
        document.body.classList.add('dark');
      }
    }

    function markdownToHtml(md) {
      const src = (md || '').replace(/\\r/g, '');
      const lines = src.split('\\n');
      let html = '';
      let inList = false;
      let inCode = false;
      for (let line of lines) {
        if (line.startsWith('```')) {
          if (!inCode) {
            inCode = true;
            html += '<pre><code>';
          } else {
            inCode = false;
            html += '</code></pre>';
          }
          continue;
        }
        if (inCode) {
          html += escapeHtml(line) + '\\n';
          continue;
        }
        if (/^###\\s+/.test(line)) { if (inList) { html += '</ul>'; inList = false; } html += `<h3>${escapeHtml(line.replace(/^###\\s+/, ''))}</h3>`; continue; }
        if (/^##\\s+/.test(line)) { if (inList) { html += '</ul>'; inList = false; } html += `<h2>${escapeHtml(line.replace(/^##\\s+/, ''))}</h2>`; continue; }
        if (/^#\\s+/.test(line)) { if (inList) { html += '</ul>'; inList = false; } html += `<h1>${escapeHtml(line.replace(/^#\\s+/, ''))}</h1>`; continue; }
        if (/^[-*]\\s+/.test(line)) {
          if (!inList) { html += '<ul>'; inList = true; }
          const text = line.replace(/^[-*]\\s+/, '');
          html += `<li>${inlineFormat(text)}</li>`;
          continue;
        }
        if (inList) { html += '</ul>'; inList = false; }
        if (!line.trim()) { html += '<p></p>'; continue; }
        html += `<p>${inlineFormat(line)}</p>`;
      }
      if (inList) html += '</ul>';
      if (inCode) html += '</code></pre>';
      return html;
    }

    function inlineFormat(text) {
      let s = escapeHtml(text);
      s = s.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
      s = s.replace(/\\*(.+?)\\*/g, '<em>$1</em>');
      s = s.replace(/`(.+?)`/g, '<code>$1</code>');
      s = s.replace(/\\[(.+?)\\]\\((https?:\\/\\/[^\\s)]+)\\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
      return s;
    }

    function reportToMarkdown(r) {
      const lines = [];
      lines.push(`# ${r.title || '未命名报告'}`);
      lines.push('');
      lines.push(`- **关键词**：${r.keyword || '-'}`);
      lines.push(`- **时间范围**：${r.time_range?.start || '-'} ~ ${r.time_range?.end || '-'}`);
      lines.push(`- **来源**：${(r.sources || []).join('、') || '-'}`);
      lines.push(`- **条目数**：${r.items_count || 0}`);
      lines.push('');
      lines.push('## 趋势分析');
      lines.push(r.analysis || '暂无分析内容');
      lines.push('');
      lines.push('## 关键条目');
      if (!r.items || !r.items.length) {
        lines.push('- 暂无条目');
      } else {
        for (const item of r.items.slice(0, 12)) {
          lines.push(`- **${item.title || '未命名'}**（${item.source || '-'}）`);
          lines.push(`  - 发布时间：${item.published_at || '-'}`);
          if (item.price !== undefined && item.price !== null) lines.push(`  - 价格：${item.price} ${item.currency || ''}`.trim());
          if (item.summary) lines.push(`  - 摘要：${item.summary}`);
          if (item.url) lines.push(`  - 链接：[查看原文](${item.url})`);
        }
      }
      return lines.join('\\n');
    }

    function renderReportList(data) {
      const list = document.getElementById('report-list');
      list.innerHTML = '';
      document.getElementById('report-count').textContent = `共 ${data.length} 条报告`;
      if (!data.length) {
        list.innerHTML = '<li class="empty">暂无报告，请先让 OpenClaw 提交报告。</li>';
        return;
      }
      for (const r of data) {
        const li = document.createElement('li');
        li.className = 'report-item' + (activeIngestId === r.ingest_id ? ' active' : '');
        li.onclick = async (e) => {
          if (e.target && e.target.classList.contains('row-check')) return;
          await loadDetail(r.ingest_id);
        };
        li.innerHTML = `
          <input type="checkbox" class="row-check" data-id="${escapeHtml(r.ingest_id || '')}" ${selectedIds.has(r.ingest_id) ? 'checked' : ''} />
          <div>
            <div class="report-title">${escapeHtml(r.title || '未命名报告')}</div>
            <div class="report-meta">关键词：${escapeHtml(r.keyword || '-')}</div>
            <div class="report-meta">时间：${escapeHtml(r.generated_at || '-')}</div>
          </div>
        `;
        const checkbox = li.querySelector('.row-check');
        checkbox?.addEventListener('click', (ev) => ev.stopPropagation());
        checkbox?.addEventListener('change', (ev) => {
          const checked = ev.target.checked;
          const id = ev.target.getAttribute('data-id');
          if (!id) return;
          if (checked) selectedIds.add(id); else selectedIds.delete(id);
        });
        list.appendChild(li);
      }
    }

    function getFilteredReports() {
      const keyword = document.getElementById('keyword-search').value.trim().toLowerCase();
      if (!keyword) return reportCache;
      return reportCache.filter((r) => String(r.keyword || '').toLowerCase().includes(keyword) || String(r.title || '').toLowerCase().includes(keyword));
    }

    async function loadReports() {
      try {
        const res = await fetch('/api/v1/public/reports');
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        reportCache = Array.isArray(data) ? data : [];
        const filtered = getFilteredReports();
        renderReportList(filtered);
        const qId = getReportIdFromQuery();
        let pick = null;
        if (qId && reportCache.some((r) => r.ingest_id === qId)) {
          pick = qId;
        } else if (filtered.length) {
          pick = filtered[0].ingest_id;
        }
        if (pick) {
          await loadDetail(pick);
        }
      } catch (err) {
        document.getElementById('report-count').textContent = '加载失败';
        document.getElementById('report-list').innerHTML = `<li class="empty">报告加载失败：${escapeHtml(err?.message || '未知错误')}</li>`;
        document.getElementById('report-detail').innerHTML = '<div class="detail-wrap muted">请检查服务是否正常，或点击“刷新”重试。</div>';
      }
    }

    async function loadDetail(ingestId) {
      try {
        const res = await fetch(`/api/v1/public/reports/${ingestId}`);
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const r = await res.json();
        activeIngestId = ingestId;
        renderReportList(getFilteredReports());
        const md = r.report_markdown || reportToMarkdown(r);
        document.getElementById('report-detail').innerHTML = markdownToHtml(md);
        try {
          const url = new URL(window.location.href);
          if (url.searchParams.get('page') === 'topic') {
            url.searchParams.set('report', ingestId);
            history.replaceState(null, '', url.pathname + url.search);
          }
        } catch (e) {
          /* ignore */
        }
      } catch (err) {
        document.getElementById('report-detail').innerHTML = `<div class="detail-wrap muted">详情加载失败：${escapeHtml(err?.message || '未知错误')}</div>`;
      }
    }

    async function deleteSelectedReports() {
      if (!selectedIds.size) {
        alert('请先勾选需要删除的报告。');
        return;
      }
      if (!confirm(`确认删除选中的 ${selectedIds.size} 条报告吗？`)) return;
      try {
        const res = await fetch('/api/v1/public/reports/bulk-delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ingest_ids: Array.from(selectedIds) }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        selectedIds.clear();
        activeIngestId = null;
        document.getElementById('report-detail').innerHTML = '<div class="detail-wrap muted">删除成功，请从左侧选择一个报告。</div>';
        await loadReports();
      } catch (err) {
        alert(`删除失败：${err?.message || '未知错误'}`);
      }
    }

    document.getElementById('keyword-search').addEventListener('input', () => {
      renderReportList(getFilteredReports());
    });

    window.addEventListener('error', (e) => {
      document.getElementById('report-count').textContent = '页面脚本异常';
      document.getElementById('report-list').innerHTML = `<li class="empty">前端脚本异常：${escapeHtml(e.message || 'unknown')}</li>`;
    });

    setupDarkMode();
    loadReports();
  </script>
</body>
</html>
"""
    )


def _rendered_root() -> Path:
    return Path(settings.content_rendered_dir)


def _raw_root() -> Path:
    return Path(settings.content_raw_dir)


def _require_public_reports_db() -> None:
    """新闻动态 API 仅从 PostgreSQL 读取；未配置 DSN 时拒绝请求。"""
    if not settings.database_url:
        raise HTTPException(
            status_code=503,
            detail="未配置 OPENCLAW_DATABASE_URL，新闻动态接口仅从数据库提供服务。",
        )


def _list_reports_from_db() -> list[dict]:
    import psycopg

    sql = """
    SELECT ingest_id, payload_json->'rendered_payload' AS rendered_payload, generated_at
    FROM reports
    WHERE status = 'published'
      AND payload_json ? 'rendered_payload'
    ORDER BY generated_at DESC NULLS LAST, id DESC
    """
    out: list[dict] = []
    with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute(sql)
        for ingest_id, rendered_payload, generated_at in cur.fetchall():
            payload = rendered_payload or {}
            out.append(
                {
                    "ingest_id": str(ingest_id),
                    "title": payload.get("title"),
                    "keyword": payload.get("keyword"),
                    "generated_at": payload.get("generated_at") or (generated_at.isoformat() if generated_at else None),
                }
            )
    return out


def _require_public_news_db() -> None:
    if not settings.news_database_url:
        raise HTTPException(
            status_code=503,
            detail="未配置 OPENCLAW_NEWS_DATABASE_URL，新闻库接口不可用。",
        )


def _list_news_library_from_db(limit: int = 100, keyword: str | None = None) -> list[dict]:
    import psycopg

    sql = """
    SELECT id, keyword, summary, source_url, title, source_name, published_at, created_at
    FROM news_library
    """
    params: list = []
    if keyword and keyword.strip():
        sql += " WHERE keyword ILIKE %s"
        params.append(f"%{keyword.strip()}%")
    sql += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)

    out: list[dict] = []
    with psycopg.connect(settings.news_database_url) as conn, conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        for row in cur.fetchall():
            out.append(
                {
                    "id": int(row[0]),
                    "keyword": row[1],
                    "summary": row[2],
                    "source_url": row[3],
                    "title": row[4],
                    "source_name": row[5],
                    "published_at": row[6].isoformat() if row[6] else None,
                    "created_at": row[7].isoformat() if row[7] else None,
                }
            )
    return out


def _delete_news_library_from_db(ids: list[int]) -> dict:
    import psycopg

    if not settings.news_database_url:
        return {"requested": len(ids), "deleted": [], "not_found": ids}
    deleted: list[int] = []
    not_found: list[int] = []
    sql = "DELETE FROM news_library WHERE id = %s RETURNING id"
    with psycopg.connect(settings.news_database_url) as conn, conn.cursor() as cur:
        for item_id in ids:
            cur.execute(sql, (int(item_id),))
            row = cur.fetchone()
            if row:
                deleted.append(int(row[0]))
            else:
                not_found.append(int(item_id))
        conn.commit()
    return {"requested": len(ids), "deleted": deleted, "not_found": not_found}


def _get_report_detail_from_db(ingest_id: str) -> dict | None:
    import psycopg

    sql = """
    SELECT payload_json->'rendered_payload' AS rendered_payload
    FROM reports
    WHERE ingest_id = %s::uuid
      AND status = 'published'
    LIMIT 1
    """
    with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute(sql, (ingest_id,))
        row = cur.fetchone()
    if not row:
        return None
    payload = row[0] or {}
    if not payload:
        return None
    payload["report_markdown"] = _report_to_markdown(payload)
    return payload


def _delete_reports_from_db(ingest_ids: list[str]) -> dict:
    import psycopg

    deleted: list[str] = []
    not_found: list[str] = []
    sql = "DELETE FROM reports WHERE ingest_id = %s::uuid RETURNING ingest_id"
    raw_root, rendered_root = _raw_root(), _rendered_root()
    with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
        for ingest_id in ingest_ids:
            cur.execute(sql, (ingest_id,))
            row = cur.fetchone()
            if row:
                iid = str(row[0])
                deleted.append(iid)
                # Remove on-disk copies if present (ingest pipeline may still write files).
                for path in (raw_root / f"{iid}.json", rendered_root / f"{iid}.json"):
                    if path.exists():
                        path.unlink()
            else:
                not_found.append(ingest_id)
        conn.commit()
    return {
        "requested": len(ingest_ids),
        "deleted": deleted,
        "not_found": not_found,
    }


def _report_to_markdown(report: dict) -> str:
    lines: list[str] = []
    lines.append(f"# {report.get('title') or '未命名报告'}")
    lines.append("")
    lines.append(f"- **关键词**：{report.get('keyword') or '-'}")
    time_range = report.get("time_range") or {}
    lines.append(f"- **时间范围**：{time_range.get('start', '-')} ~ {time_range.get('end', '-')}")
    lines.append(f"- **来源**：{'、'.join(report.get('sources') or []) or '-'}")
    lines.append(f"- **条目数**：{report.get('items_count') or 0}")
    lines.append("")
    lines.append("## 趋势分析")
    lines.append(report.get("analysis") or "暂无分析内容")
    lines.append("")
    lines.append("## 关键条目")
    items = report.get("items") or []
    if not items:
        lines.append("- 暂无条目")
    else:
        for item in items[:12]:
            lines.append(f"- **{item.get('title') or '未命名'}**（{item.get('source') or '-'}）")
            lines.append(f"  - 发布时间：{item.get('published_at') or '-'}")
            if item.get("price") is not None:
                lines.append(f"  - 价格：{item.get('price')} {item.get('currency') or ''}".rstrip())
            if item.get("summary"):
                lines.append(f"  - 摘要：{item.get('summary')}")
            if item.get("url"):
                lines.append(f"  - 链接：[查看原文]({item.get('url')})")
    return "\n".join(lines)


def _list_news_items_from_db(limit: int = 120) -> list[dict]:
    import psycopg

    sql = """
    SELECT ingest_id, payload_json->'rendered_payload' AS rendered_payload, generated_at
    FROM reports
    WHERE status = 'published'
      AND payload_json ? 'rendered_payload'
    ORDER BY generated_at DESC NULLS LAST, id DESC
    LIMIT 200
    """
    out: list[dict] = []
    with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    for ingest_id, rendered_payload, generated_at in rows:
        payload = rendered_payload or {}
        items = payload.get("items") or []
        for item in items:
            out.append(
                {
                    "ingest_id": str(ingest_id),
                    "report_title": payload.get("title") or payload.get("generated_title") or "未命名报告",
                    "keyword": payload.get("keyword"),
                    "generated_at": payload.get("generated_at") or (generated_at.isoformat() if generated_at else None),
                    "title": item.get("title"),
                    "source": item.get("source"),
                    "url": item.get("url"),
                    "published_at": item.get("published_at"),
                    "summary": item.get("summary"),
                    "price": item.get("price"),
                    "currency": item.get("currency"),
                }
            )
            if len(out) >= limit:
                return out
    return out


def _topic_analysis_cards_from_db(limit: int = 60) -> list[dict]:
    import psycopg

    sql = """
    SELECT ingest_id, payload_json->'rendered_payload' AS rendered_payload, generated_at
    FROM reports
    WHERE status = 'published'
      AND payload_json ? 'rendered_payload'
    ORDER BY generated_at DESC NULLS LAST, id DESC
    LIMIT %s
    """
    out: list[dict] = []
    with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
        cur.execute(sql, (limit,))
        for ingest_id, rendered_payload, generated_at in cur.fetchall():
            payload = rendered_payload or {}
            out.append(
                {
                    "ingest_id": str(ingest_id),
                    "title": payload.get("title") or payload.get("generated_title") or "未命名专题",
                    "keyword": payload.get("keyword"),
                    "generated_at": payload.get("generated_at") or (generated_at.isoformat() if generated_at else None),
                    "analysis": payload.get("analysis") or "暂无分析内容",
                    "items_count": payload.get("items_count") or len(payload.get("items") or []),
                    "sources": payload.get("sources") or [],
                }
            )
    return out


def _list_monitors_public() -> list[dict]:
    import psycopg

    if not settings.monitoring_database_url:
        return []
    sql = """
    SELECT
      m.monitor_id,
      m.keyword,
      m.cadence,
      m.created_at,
      COUNT(DISTINCT u.id) AS url_count,
      COUNT(o.id) AS observation_count,
      MAX(o.captured_at) AS last_captured_at
    FROM price_monitors m
    LEFT JOIN price_monitor_urls u ON u.monitor_id = m.monitor_id
    LEFT JOIN price_observations o ON o.monitor_id = m.monitor_id
    GROUP BY m.monitor_id, m.keyword, m.cadence, m.created_at
    ORDER BY m.created_at DESC
    """
    out: list[dict] = []
    with psycopg.connect(settings.monitoring_database_url) as conn, conn.cursor() as cur:
        cur.execute(sql)
        for row in cur.fetchall():
            out.append(
                {
                    "monitor_id": str(row[0]),
                    "keyword": row[1],
                    "cadence": row[2],
                    "created_at": row[3].isoformat() if row[3] else None,
                    "url_count": int(row[4] or 0),
                    "observation_count": int(row[5] or 0),
                    "last_captured_at": row[6].isoformat() if row[6] else None,
                }
            )
    return out


def _monitor_timeseries_public(monitor_id: str, window_days: int) -> dict:
    import psycopg

    if not settings.monitoring_database_url:
        return {"monitor_id": monitor_id, "points": []}
    sql = """
    SELECT
      DATE_TRUNC('day', captured_at) AS day,
      MIN(price) AS min_price,
      MAX(price) AS max_price,
      AVG(price) AS avg_price,
      COUNT(*) AS priced_count
    FROM price_observations
    WHERE monitor_id = %s::uuid
      AND captured_at >= NOW() - (%s || ' days')::interval
      AND price IS NOT NULL
    GROUP BY DATE_TRUNC('day', captured_at)
    ORDER BY day ASC
    """
    points: list[dict] = []
    with psycopg.connect(settings.monitoring_database_url) as conn, conn.cursor() as cur:
        cur.execute(sql, (monitor_id, int(window_days)))
        for day, min_price, max_price, avg_price, priced_count in cur.fetchall():
            points.append(
                {
                    "date": day.date().isoformat(),
                    "min_price": float(min_price) if min_price is not None else None,
                    "max_price": float(max_price) if max_price is not None else None,
                    "avg_price": float(avg_price) if avg_price is not None else None,
                    "priced_count": int(priced_count or 0),
                }
            )
    return {"monitor_id": monitor_id, "window_days": int(window_days), "points": points}


def _monitor_observations_public(monitor_id: str, limit: int = 200) -> dict:
    import psycopg

    if not settings.monitoring_database_url:
        return {"monitor_id": monitor_id, "rows": []}

    sql = """
    SELECT
      o.captured_at,
      o.title,
      o.price
    FROM price_observations o
    WHERE o.monitor_id = %s::uuid
      AND o.price IS NOT NULL
    ORDER BY o.captured_at ASC
    LIMIT %s
    """
    rows: list[dict] = []
    prev_price: float | None = None
    with psycopg.connect(settings.monitoring_database_url) as conn, conn.cursor() as cur:
        cur.execute(sql, (monitor_id, int(limit)))
        for idx, (captured_at, title, price) in enumerate(cur.fetchall(), start=1):
            p = float(price) if price is not None else None
            delta = None
            if p is not None and prev_price is not None:
                delta = p - prev_price
            if p is not None:
                prev_price = p
            rows.append(
                {
                    "index": idx,
                    "item_name": title or "未命名商品",
                    "captured_at": captured_at.isoformat() if captured_at else None,
                    "price": p,
                    "delta_from_prev": delta,
                }
            )
    return {"monitor_id": monitor_id, "rows": rows}


def _monitoring_scheduler_status_public(app_obj: FastAPI) -> dict:
    started = bool(getattr(app_obj.state, "monitoring_scheduler_started", False))
    has_db = bool(settings.monitoring_database_url)
    has_monitor = bool(settings.monitoring_scheduler_monitor_id)
    enabled = bool(settings.monitoring_scheduler_enabled)
    return {
        "mode": "internal",
        "enabled": enabled,
        "started": started,
        "configured": enabled and has_db and has_monitor,
        "monitor_id": settings.monitoring_scheduler_monitor_id,
        "interval_minutes": settings.monitoring_scheduler_interval_minutes,
        "run_on_start": settings.monitoring_scheduler_run_on_start,
        "has_monitoring_database_url": has_db,
        "allow_server_scrape": settings.monitoring_allow_server_scrape,
    }


def _external_scheduler_jobs_public(app_obj: FastAPI) -> dict:
    jobs = getattr(app_obj.state, "external_scheduler_jobs", {})
    out = []
    for job_name, item in jobs.items():
        out.append(
            {
                "job_name": job_name,
                "status": item.get("status"),
                "monitor_id": item.get("monitor_id"),
                "message": item.get("message"),
                "last_seen_at": item.get("last_seen_at"),
            }
        )
    out.sort(key=lambda x: x.get("last_seen_at") or "", reverse=True)
    return {"jobs": out}


def _openclaw_work_overview_public(app_obj: FastAPI) -> dict:
    """门户首页「工作情况」聚合：报告、价格监测、新闻库、外部 cron（不含内部 scheduler）。"""
    ext = _external_scheduler_jobs_public(app_obj)
    jobs = ext.get("jobs") or []

    reports: dict = {
        "available": False,
        "published_count": 0,
        "last_generated_at": None,
        "recent": [],
    }
    if settings.database_url:
        import psycopg

        try:
            with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*), MAX(generated_at)
                    FROM reports
                    WHERE status = 'published'
                      AND payload_json ? 'rendered_payload'
                    """
                )
                cnt, mx = cur.fetchone()
                reports["available"] = True
                reports["published_count"] = int(cnt or 0)
                reports["last_generated_at"] = mx.isoformat() if mx else None
                cur.execute(
                    """
                    SELECT ingest_id, payload_json->'rendered_payload' AS rendered_payload, generated_at
                    FROM reports
                    WHERE status = 'published'
                      AND payload_json ? 'rendered_payload'
                    ORDER BY generated_at DESC NULLS LAST, id DESC
                    LIMIT 4
                    """
                )
                recent: list[dict] = []
                for ingest_id, rendered_payload, generated_at in cur.fetchall():
                    payload = rendered_payload or {}
                    recent.append(
                        {
                            "ingest_id": str(ingest_id),
                            "title": payload.get("title")
                            or payload.get("generated_title")
                            or "未命名报告",
                            "generated_at": payload.get("generated_at")
                            or (generated_at.isoformat() if generated_at else None),
                        }
                    )
                reports["recent"] = recent
        except Exception as exc:  # noqa: BLE001
            reports["error"] = str(exc)

    price: dict = {
        "available": False,
        "monitor_count": 0,
        "observation_count": 0,
        "last_captured_at": None,
        "recent": [],
    }
    if settings.monitoring_database_url:
        import psycopg

        try:
            with psycopg.connect(settings.monitoring_database_url) as conn, conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM price_monitors")
                price["monitor_count"] = int(cur.fetchone()[0] or 0)
                cur.execute("SELECT COUNT(*), MAX(captured_at) FROM price_observations")
                oc, lc = cur.fetchone()
                price["observation_count"] = int(oc or 0)
                price["last_captured_at"] = lc.isoformat() if lc else None
                cur.execute(
                    """
                    SELECT
                      m.monitor_id,
                      m.keyword,
                      COUNT(o.id) AS observation_count,
                      MAX(o.captured_at) AS last_captured_at
                    FROM price_monitors m
                    LEFT JOIN price_observations o ON o.monitor_id = m.monitor_id
                    GROUP BY m.monitor_id, m.keyword, m.created_at
                    ORDER BY MAX(o.captured_at) DESC NULLS LAST, m.created_at DESC
                    LIMIT 6
                    """
                )
                recent_monitors: list[dict] = []
                for monitor_id, keyword, obs_count, last_ts in cur.fetchall():
                    recent_monitors.append(
                        {
                            "monitor_id": str(monitor_id),
                            "keyword": keyword,
                            "observation_count": int(obs_count or 0),
                            "last_captured_at": last_ts.isoformat() if last_ts else None,
                        }
                    )
                price["recent"] = recent_monitors
                price["available"] = True
        except Exception as exc:  # noqa: BLE001
            price["error"] = str(exc)

    news: dict = {
        "available": False,
        "item_count": 0,
        "last_created_at": None,
        "recent_keywords": [],
    }
    if settings.news_database_url:
        import psycopg

        try:
            with psycopg.connect(settings.news_database_url) as conn, conn.cursor() as cur:
                cur.execute("SELECT COUNT(*), MAX(created_at) FROM news_library")
                ic, mx = cur.fetchone()
                news["item_count"] = int(ic or 0)
                news["last_created_at"] = mx.isoformat() if mx else None
                cur.execute(
                    """
                    SELECT
                      keyword,
                      COUNT(*) AS item_count,
                      MAX(COALESCE(published_at, created_at)) AS last_event_at,
                      MAX(created_at) AS last_created_at
                    FROM news_library
                    GROUP BY keyword
                    ORDER BY MAX(COALESCE(published_at, created_at)) DESC NULLS LAST
                    LIMIT 6
                    """
                )
                recent_keywords: list[dict] = []
                for keyword, item_count, last_event_at, last_created_at in cur.fetchall():
                    recent_keywords.append(
                        {
                            "keyword": keyword,
                            "item_count": int(item_count or 0),
                            "last_event_at": last_event_at.isoformat() if last_event_at else None,
                            "last_created_at": last_created_at.isoformat() if last_created_at else None,
                        }
                    )
                news["recent_keywords"] = recent_keywords
                news["available"] = True
        except Exception as exc:  # noqa: BLE001
            news["error"] = str(exc)

    return {
        "reports": reports,
        "price_monitoring": price,
        "news_library": news,
        "external_cron": {"job_count": len(jobs), "jobs": jobs},
        "refresh_hint_seconds": 1800,
    }


def _parse_iso_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except Exception:  # noqa: BLE001
        return None


def _sentiment_from_text(text: str) -> str:
    lower = text.lower()
    positive = ("上涨", "走强", "利好", "增持", "突破", "反弹", "上调", "紧张", "减产")
    negative = ("下跌", "走弱", "利空", "抛售", "回落", "暴跌", "下调", "宽松", "增产")
    p = sum(1 for token in positive if token in lower)
    n = sum(1 for token in negative if token in lower)
    if p > n:
        return "bullish"
    if n > p:
        return "bearish"
    return "neutral"


def _build_news_price_analysis(
    monitor_id: str,
    keyword: str | None,
    window_days: int,
    news_hours: int,
    horizon: str,
) -> dict:
    if not settings.monitoring_database_url:
        raise HTTPException(status_code=503, detail="未配置 OPENCLAW_MONITORING_DATABASE_URL。")
    _require_public_news_db()

    summary = MonitoringService(settings.monitoring_database_url).get_summary(
        monitor_id=monitor_id,
        window_days=window_days,
    )
    effective_keyword = (keyword or summary.get("keyword") or "").strip()
    if not effective_keyword:
        effective_keyword = "未命名关键词"

    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=max(1, news_hours))
    recent_news = []
    for item in _list_news_library_from_db(limit=300, keyword=effective_keyword):
        ts = _parse_iso_dt(item.get("published_at")) or _parse_iso_dt(item.get("created_at"))
        if not ts:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts >= since:
            recent_news.append(item)
    recent_news.sort(
        key=lambda x: (_parse_iso_dt(x.get("published_at")) or _parse_iso_dt(x.get("created_at")) or now),
        reverse=True,
    )
    key_news = recent_news[:5]

    bullish = 0
    bearish = 0
    neutral = 0
    for row in key_news:
        txt = f"{row.get('title') or ''} {row.get('summary') or ''}"
        s = _sentiment_from_text(txt)
        if s == "bullish":
            bullish += 1
        elif s == "bearish":
            bearish += 1
        else:
            neutral += 1

    min_price = summary.get("min_price")
    max_price = summary.get("max_price")
    latest_price = summary.get("latest_price")
    trend = "震荡"
    if isinstance(min_price, (int, float)) and isinstance(max_price, (int, float)) and isinstance(latest_price, (int, float)):
        mid = (float(min_price) + float(max_price)) / 2.0
        if latest_price > mid * 1.02:
            trend = "偏强"
        elif latest_price < mid * 0.98:
            trend = "偏弱"

    forecast = "震荡"
    if bullish > bearish:
        forecast = "上行"
    elif bearish > bullish:
        forecast = "下行"
    elif trend == "偏强":
        forecast = "上行"
    elif trend == "偏弱":
        forecast = "下行"

    priced_obs = int(summary.get("priced_observations") or 0)
    confidence = "低"
    if priced_obs >= 20 and len(key_news) >= 2:
        confidence = "高"
    elif priced_obs >= 5 and len(key_news) >= 1:
        confidence = "中"

    evidence_lines = []
    for row in key_news[:3]:
        evidence_lines.append(
            f"- {row.get('title') or '未命名新闻'} | {row.get('source_name') or '未知来源'} | {row.get('source_url') or '-'}"
        )
    news_evidence = "\n".join(evidence_lines) if evidence_lines else "- 最近窗口无高相关新增新闻。"
    analysis = (
        f"{effective_keyword} 在近{window_days}天价格区间为 {summary.get('min_price')}~{summary.get('max_price')}，"
        f"最新价格 {summary.get('latest_price')}，当前走势判断为{trend}。"
        f"结合近{news_hours}小时新闻（利多{bullish} / 利空{bearish} / 中性{neutral}），"
        f"预测未来{horizon}倾向{forecast}，置信度{confidence}。"
        f"若后续出现与当前判断相反的高优先级事件，结论可能快速失效。\n\n关键新闻证据：\n{news_evidence}"
    )

    return {
        "monitor_id": monitor_id,
        "keyword": effective_keyword,
        "window_days": window_days,
        "news_hours": news_hours,
        "horizon": horizon,
        "summary": summary,
        "news_count": len(recent_news),
        "key_news": key_news,
        "forecast": forecast,
        "confidence": confidence,
        "analysis": analysis,
    }


@app.get("/api/v1/public/reports", summary="用户侧报告列表")
def list_reports() -> list[dict]:
    _require_public_reports_db()
    return _list_reports_from_db()


@app.get("/api/v1/public/reports/{ingest_id}", summary="用户侧报告详情")
def get_report_detail(ingest_id: str) -> dict:
    _require_public_reports_db()
    payload = _get_report_detail_from_db(ingest_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return payload


@app.get("/api/v1/public/news/library", summary="用户侧新闻库列表")
def public_news_library(limit: int = 100, keyword: str | None = None) -> list[dict]:
    _require_public_news_db()
    cap = max(1, min(int(limit), 500))
    return _list_news_library_from_db(limit=cap, keyword=keyword)


@app.post("/api/v1/public/news/library/bulk-delete", summary="用户侧批量删除新闻库条目")
def public_news_library_bulk_delete(request: NewsBulkDeleteRequest) -> dict:
    _require_public_news_db()
    return _delete_news_library_from_db(request.ids)


@app.get("/api/v1/public/news/items", summary="用户侧新闻通道条目")
def public_news_items(limit: int = 120) -> list[dict]:
    _require_public_reports_db()
    cap = max(1, min(int(limit), 300))
    return _list_news_items_from_db(limit=cap)


@app.get("/api/v1/public/topic/cards", summary="用户侧专题分析卡片")
def public_topic_cards(limit: int = 60) -> list[dict]:
    _require_public_reports_db()
    cap = max(1, min(int(limit), 200))
    return _topic_analysis_cards_from_db(limit=cap)


@app.get("/api/v1/public/monitoring/scheduler-status", summary="用户侧定时任务状态")
def public_monitoring_scheduler_status() -> dict:
    return _monitoring_scheduler_status_public(app)


@app.get("/api/v1/public/monitoring/external-jobs", summary="用户侧外部定时任务心跳")
def public_monitoring_external_jobs() -> dict:
    return _external_scheduler_jobs_public(app)


@app.get(
    "/api/v1/public/portal/openclaw-work-overview",
    summary="门户首页 OpenClaw 工作情况聚合",
)
def public_openclaw_work_overview() -> dict:
    return _openclaw_work_overview_public(app)


@app.get("/api/v1/public/monitoring/monitors", summary="用户侧关键词监测总览")
def public_monitoring_monitors() -> list[dict]:
    return _list_monitors_public()


@app.get("/api/v1/public/monitoring/{monitor_id}/timeseries", summary="用户侧价格时序数据")
def public_monitoring_timeseries(monitor_id: str, window_days: int = 30) -> dict:
    cap_days = max(1, min(int(window_days), 365))
    return _monitor_timeseries_public(monitor_id=monitor_id, window_days=cap_days)


@app.get("/api/v1/public/monitoring/{monitor_id}/observations", summary="用户侧价格采集明细")
def public_monitoring_observations(monitor_id: str, limit: int = 200) -> dict:
    cap_limit = max(1, min(int(limit), 1000))
    return _monitor_observations_public(monitor_id=monitor_id, limit=cap_limit)


@app.post("/api/v1/openclaw/monitoring/external-heartbeat", summary="上报外部定时任务心跳")
def report_external_scheduler_heartbeat(
    payload: ExternalSchedulerHeartbeatRequest,
    request: Request,
    _: None = Depends(verify_api_key),
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    request.app.state.external_scheduler_jobs[payload.job_name] = {
        "status": payload.status,
        "monitor_id": payload.monitor_id,
        "message": payload.message,
        "last_seen_at": now,
    }
    return {"ok": True, "job_name": payload.job_name, "last_seen_at": now}


@app.post("/api/v1/openclaw/analysis/news-trigger", summary="新闻触发价格联合分析")
def trigger_news_price_analysis(
    payload: NewsTriggerAnalysisRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_api_key),
) -> dict:
    window_days = max(1, min(int(payload.window_days), 365))
    news_hours = max(1, min(int(payload.news_hours), 24 * 30))
    result = _build_news_price_analysis(
        monitor_id=payload.monitor_id,
        keyword=payload.keyword,
        window_days=window_days,
        news_hours=news_hours,
        horizon=payload.horizon,
    )
    ingest_id = None
    ingest_status = None
    if payload.publish:
        now = datetime.now(timezone.utc)
        report = OpenClawReportIn(
            task_id=f"news-trigger-{payload.monitor_id}-{int(now.timestamp())}",
            keyword=result["keyword"],
            time_range={"start": (now - timedelta(days=window_days)), "end": now},
            sources=["monitoring-summary", "news-library"],
            items=[
                {
                    "title": n.get("title") or "未命名新闻",
                    "source": n.get("source_name") or "unknown",
                    "url": n.get("source_url") or "",
                    "published_at": _parse_iso_dt(n.get("published_at"))
                    or _parse_iso_dt(n.get("created_at"))
                    or now,
                    "summary": n.get("summary"),
                }
                for n in result["key_news"]
                if n.get("source_url")
            ],
            analysis=result["analysis"],
            generated_title=f"{result['keyword']} 新闻触发价格分析（{payload.horizon}）",
            generated_at=now,
        )
        ingest_id, ingest_status = intake_service.ingest(
            report=report,
            request_id=f"news-trigger-{payload.monitor_id}-{int(now.timestamp())}",
            background_tasks=background_tasks,
        )

    return {
        "ok": True,
        "mode": "event_triggered",
        "publish": payload.publish,
        "ingest_id": ingest_id,
        "ingest_status": ingest_status,
        **result,
    }


@app.post("/api/v1/public/reports/bulk-delete", summary="批量删除报告")
def bulk_delete_reports(request: BulkDeleteRequest) -> dict:
    _require_public_reports_db()
    return _delete_reports_from_db(request.ingest_ids)


def _coming_soon_page(title: str, active_nav_key: str) -> HTMLResponse:
    return HTMLResponse(
        f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <style>
    :root {{
      --bg: #f7f8fb;
      --surface: #ffffff;
      --surface-2: #f1f3f7;
      --text: #1f2937;
      --muted: #6b7280;
      --line: #d8dee8;
      --brand: #0b4fa3;
      --link: #164b91;
      --header: #0a2f66;
      --header-text: #ffffff;
    }}
    body.dark {{
      --bg: #0f1218;
      --surface: #171c25;
      --surface-2: #202735;
      --text: #e6edf7;
      --muted: #9fb0c9;
      --line: #2c3444;
      --brand: #66a3ff;
      --link: #8eb8ff;
      --header: #101624;
      --header-text: #f3f6fd;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    .topbar {{
      background: var(--header);
      color: var(--header-text);
      border-bottom: 1px solid rgba(255,255,255,0.15);
    }}
    .wrap {{ width:min(1200px,100% - 28px); margin: 0 auto; }}
    .topbar-inner {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 0;
    }}
    .logo {{ font-size: 20px; font-weight: 700; letter-spacing: .5px; }}
    .top-actions {{ display: flex; gap: 10px; align-items: center; }}
    .top-actions button {{
      border: 1px solid rgba(255,255,255,.35);
      background: rgba(255,255,255,.08);
      color: var(--header-text);
      padding: 7px 12px;
      border-radius: 12px;
      cursor: pointer;
      font-size: 14px;
    }}
    .nav {{
      background: var(--surface);
      border-bottom: 1px solid var(--line);
      margin-bottom: 14px;
    }}
    .nav ul {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      gap: 18px;
      overflow-x: auto;
      white-space: nowrap;
    }}
    .nav li, .nav a {{
      padding: 12px 0;
      border-bottom: 2px solid transparent;
      cursor: pointer;
      color: inherit;
      display: inline-block;
      text-decoration: none;
    }}
    .nav li.active {{ border-color: var(--brand); color: var(--brand); font-weight: 600; }}

    .content-wrap {{ width:min(960px,100% - 28px); margin: 18px auto 0; }}
    .box {{
      background: var(--surface);
      border: 1px solid var(--line);
      padding: 24px;
      border-radius: 16px;
    }}
    h1 {{ margin:0 0 10px; color: var(--brand); }}
    p {{ margin: 0; }}
    .muted {{ color: var(--muted); margin-top: 8px; }}
    .btn-link {{
      display: inline-block;
      margin-top: 16px;
      padding: 10px 14px;
      border: 1px solid var(--line);
      background: var(--surface-2);
      color: var(--text);
      border-radius: 14px;
      text-decoration: none;
      font-weight: 650;
    }}
  </style>
</head>
<body>
  <div class="topbar">
    <div class="wrap topbar-inner">
      <div class="logo">OpenClaw市场趋势自动化分析平台</div>
      <div class="top-actions">
        <button onclick="toggleDarkMode()">暗色模式</button>
        <button onclick="location.href='/docs'">接口文档</button>
      </div>
    </div>
  </div>

  <div class="nav">
    <div class="wrap">
      <ul id="category-nav">
        <li{ ' class="active"' if active_nav_key == "home" else ""}><a href="/">门户首页</a></li>
        <li{ ' class="active"' if active_nav_key == "news" else ""}><a href="/?page=news">新闻动态</a></li>
        <li{ ' class="active"' if active_nav_key == "price" else ""}><a href="/price-trend">价格趋势</a></li>
        <li{ ' class="active"' if active_nav_key == "topic" else ""}><a href="/topic-analysis">专题分析</a></li>
        <li{ ' class="active"' if active_nav_key == "keyword" else ""}><a href="/keyword-tracking">监测参数</a></li>
      </ul>
    </div>
  </div>

  <div class="content-wrap">
    <div class="box">
      <h1>{title}</h1>
      <p class="muted">该页面正在开发中，敬请期待。</p>
      <a class="btn-link" href="/">返回门户首页</a>
    </div>
  </div>

  <script>
    function toggleDarkMode() {{
      document.body.classList.toggle('dark');
      localStorage.setItem('oc_dark', document.body.classList.contains('dark') ? '1' : '0');
    }}
    function setupDarkMode() {{
      if (localStorage.getItem('oc_dark') === '1') {{
        document.body.classList.add('dark');
      }}
    }}
    setupDarkMode();
  </script>
</body>
</html>
"""
    )


@app.get("/topic-analysis", summary="专题分析页面")
def topic_analysis_page() -> HTMLResponse:
    return RedirectResponse(url="/?page=topic")


@app.get("/price-trend", summary="价格趋势页面")
def price_trend_page() -> HTMLResponse:
    return HTMLResponse(
        """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>价格趋势</title>
  <style>
    :root {
      --bg: #f7f8fb;
      --surface: #ffffff;
      --surface-2: #f1f3f7;
      --text: #1f2937;
      --muted: #6b7280;
      --line: #d8dee8;
      --brand: #0b4fa3;
      --brand-soft: #dbeafe;
      --header: #0a2f66;
      --header-text: #ffffff;
      --chart-grid: #d8dee8;
      --chart-font: "Inter", "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    }
    body.dark {
      --bg: #0f1218;
      --surface: #171c25;
      --surface-2: #202735;
      --text: #e6edf7;
      --muted: #9fb0c9;
      --line: #2c3444;
      --brand: #66a3ff;
      --brand-soft: #1c2b45;
      --header: #101624;
      --header-text: #f3f6fd;
      --chart-grid: #334155;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    .wrap { width: min(1200px, 100% - 28px); margin: 0 auto; }
    .topbar {
      background: var(--header);
      color: var(--header-text);
      border-bottom: 1px solid rgba(255,255,255,0.15);
    }
    .topbar-inner { display: flex; align-items: center; justify-content: space-between; padding: 12px 0; }
    .logo { font-size: 20px; font-weight: 700; letter-spacing: .5px; }
    .top-actions { display: flex; gap: 8px; }
    .top-actions button {
      border: 1px solid rgba(255,255,255,.35);
      background: rgba(255,255,255,.08);
      color: var(--header-text);
      padding: 7px 12px;
      border-radius: 12px;
      cursor: pointer;
      font-size: 14px;
    }
    .nav { background: var(--surface); border-bottom: 1px solid var(--line); margin-bottom: 14px; }
    .nav ul { list-style: none; margin: 0; padding: 0; display: flex; gap: 18px; overflow-x: auto; white-space: nowrap; }
    .nav li, .nav a { padding: 12px 0; border-bottom: 2px solid transparent; cursor: pointer; color: inherit; display: inline-block; text-decoration: none; }
    .nav li.active { border-color: var(--brand); color: var(--brand); font-weight: 600; }
    .page { display: grid; grid-template-columns: 340px 1fr; gap: 18px; padding-bottom: 20px; }
    .left, .right { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; }
    .panel-title {
      margin: 0;
      font-size: 18px;
      border-bottom: 1px solid var(--line);
      padding: 12px 14px;
      background: var(--surface-2);
      color: var(--brand);
    }
    .toolbar { display: flex; gap: 8px; padding: 10px 14px; border-bottom: 1px solid var(--line); align-items: center; }
    .toolbar input, .toolbar select, .toolbar button {
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--text);
      padding: 7px 10px;
      border-radius: 12px;
      font-size: 14px;
    }
    #monitor-list { list-style: none; margin: 0; padding: 0; max-height: calc(100vh - 245px); overflow: auto; }
    .monitor-item {
      padding: 12px 14px;
      border-bottom: 1px dashed var(--line);
      cursor: pointer;
      background: var(--surface);
    }
    .monitor-item:hover { background: var(--surface-2); }
    .monitor-item.active { border-left: 3px solid var(--brand); background: var(--surface-2); }
    .monitor-title { font-size: 15px; line-height: 1.45; margin-bottom: 4px; }
    .monitor-meta { color: var(--muted); font-size: 12px; }
    .right-wrap { padding: 12px 14px 16px; }
    .detail-title { margin: 0 0 10px; color: var(--brand); }
    .muted { color: var(--muted); }
    .chart-wrap { position: relative; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); padding: 10px; margin-bottom: 12px; box-shadow: inset 0 1px 0 rgba(255,255,255,0.06); }
    canvas { width: 100%; height: 320px; display: block; }
    .chart-tooltip {
      position: absolute;
      pointer-events: none;
      display: none;
      z-index: 20;
      background: rgba(15, 23, 42, 0.92);
      color: #e5e7eb;
      border: 1px solid rgba(148, 163, 184, 0.3);
      border-radius: 10px;
      padding: 8px 10px;
      font-size: 12px;
      line-height: 1.4;
      white-space: nowrap;
      box-shadow: 0 8px 24px rgba(0,0,0,0.38);
      font-family: var(--chart-font);
    }
    table { width: 100%; border-collapse: collapse; border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
    th, td { padding: 9px 10px; border-bottom: 1px solid var(--line); text-align: left; font-size: 13px; }
    th { background: var(--surface-2); }
    .delta-up { color: #b42318; font-weight: 600; }
    .delta-down { color: #127a38; font-weight: 600; }
    .delta-flat { color: var(--muted); }
    .empty { padding: 14px; color: var(--muted); }
    .obs-pager { display:flex; align-items:center; justify-content:space-between; gap:8px; margin:8px 0 2px; }
    .obs-page-meta { color:var(--muted); font-size:12px; }
    .obs-pager-actions { display:flex; gap:8px; }
    .obs-pager-actions button { border:1px solid var(--line); background:var(--surface); color:var(--text); padding:6px 10px; border-radius:10px; cursor:pointer; font-size:12px; }
    .obs-pager-actions button:disabled { opacity:.45; cursor:not-allowed; }
    @media (max-width: 920px) {
      .page { grid-template-columns: 1fr; }
      #monitor-list { max-height: 300px; }
    }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="wrap topbar-inner">
      <div class="logo">OpenClaw市场趋势自动化分析平台</div>
      <div class="top-actions">
        <button onclick="toggleDarkMode()">暗色模式</button>
        <button onclick="location.href='/docs'">接口文档</button>
      </div>
    </div>
  </div>
  <div class="nav">
    <div class="wrap">
      <ul id="category-nav">
        <li><a href="/">门户首页</a></li>
        <li><a href="/?page=news">新闻动态</a></li>
        <li class="active"><a href="/price-trend">价格趋势</a></li>
        <li><a href="/topic-analysis">专题分析</a></li>
        <li><a href="/keyword-tracking">监测参数</a></li>
      </ul>
    </div>
  </div>
  <div class="wrap">
    <div class="page">
      <div class="left">
        <h2 class="panel-title">追踪商品</h2>
        <div class="toolbar">
          <input id="monitor-search" placeholder="输入关键词筛选" />
          <button id="refresh-list-btn">刷新</button>
        </div>
        <ul id="monitor-list"></ul>
      </div>
      <div class="right">
        <h2 class="panel-title" id="right-title">价格趋势详情</h2>
        <div class="right-wrap">
          <div class="toolbar" style="padding:0 0 10px;border-bottom:none;">
            <label>窗口：</label>
            <select id="window-select">
              <option value="1">1天（24小时）</option>
              <option value="3">3天</option>
              <option value="7">7天</option>
              <option value="14">14天</option>
              <option value="30" selected>30天</option>
              <option value="90">90天</option>
            </select>
            <button id="refresh-detail-btn">刷新详情</button>
          </div>
          <div class="chart-wrap">
            <canvas id="trend-canvas" width="980" height="300"></canvas>
            <div id="chart-tooltip" class="chart-tooltip"></div>
          </div>
          <div class="muted" style="margin:0 0 8px;">数据采集记录</div>
          <div class="obs-pager">
            <div id="obs-page-meta" class="obs-page-meta">-</div>
            <div class="obs-pager-actions">
              <button id="obs-prev-btn" type="button">上一页</button>
              <button id="obs-next-btn" type="button">下一页</button>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>序号</th>
                <th>商品名</th>
                <th>数据收集时间</th>
                <th>价格</th>
                <th>较上次变化</th>
              </tr>
            </thead>
            <tbody id="obs-body">
              <tr><td colspan="5" class="empty">请选择左侧商品</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
  <script>
    let monitors = [];
    let activeMonitorId = null;
    let trendPlotPoints = [];
    let currentObservationRows = [];
    let obsPage = 1;
    const OBS_PAGE_SIZE = 100;
    let lastChartPoints = [];
    let lastChartTitle = '';
    let lastChartUnit = 'CNY';

    function escapeHtml(text) {
      return String(text ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
    }

    async function loadMonitors() {
      const res = await fetch('/api/v1/public/monitoring/monitors');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const raw = Array.isArray(data) ? data : [];
      const grouped = new Map();
      for (const m of raw) {
        const key = String(m.keyword || '').trim().toLowerCase() || '__empty__';
        const current = grouped.get(key);
        if (!current) {
          grouped.set(key, m);
          continue;
        }
        const curObs = Number(current.observation_count || 0);
        const newObs = Number(m.observation_count || 0);
        const curTs = Date.parse(current.last_captured_at || '') || 0;
        const newTs = Date.parse(m.last_captured_at || '') || 0;
        if (newObs > curObs || (newObs === curObs && newTs > curTs)) {
          grouped.set(key, m);
        }
      }
      monitors = Array.from(grouped.values()).sort((a, b) => {
        const aObs = Number(a.observation_count || 0);
        const bObs = Number(b.observation_count || 0);
        if (bObs !== aObs) return bObs - aObs;
        const aTs = Date.parse(a.last_captured_at || '') || 0;
        const bTs = Date.parse(b.last_captured_at || '') || 0;
        return bTs - aTs;
      });
      if (!activeMonitorId && monitors.length) activeMonitorId = monitors[0].monitor_id;
      if (activeMonitorId && !monitors.some((m) => m.monitor_id === activeMonitorId)) {
        activeMonitorId = monitors.length ? monitors[0].monitor_id : null;
      }
      renderMonitorList();
    }

    function renderMonitorList() {
      const list = document.getElementById('monitor-list');
      const keyword = document.getElementById('monitor-search').value.trim().toLowerCase();
      const filtered = !keyword
        ? monitors
        : monitors.filter((m) => String(m.keyword || '').toLowerCase().includes(keyword));
      list.innerHTML = '';
      if (!filtered.length) {
        list.innerHTML = '<li class="empty">暂无可用追踪商品。</li>';
        return;
      }
      for (const m of filtered) {
        const li = document.createElement('li');
        li.className = 'monitor-item' + (m.monitor_id === activeMonitorId ? ' active' : '');
        li.innerHTML = `
          <div class="monitor-title">${escapeHtml(m.keyword || '未命名商品')}</div>
          <div class="monitor-meta">monitor: ${escapeHtml((m.monitor_id || '').slice(0,8))} | 观测数：${m.observation_count || 0}</div>
          <div class="monitor-meta">最近采样：${escapeHtml(m.last_captured_at || '-')}</div>
        `;
        li.onclick = async () => {
          activeMonitorId = m.monitor_id;
          renderMonitorList();
          await loadDetail();
        };
        list.appendChild(li);
      }
    }

    function drawLine(points, title, unit = 'CNY', hoverPoint = null) {
      const canvas = document.getElementById('trend-canvas');
      const ctx = canvas.getContext('2d');
      const dpr = Math.max(window.devicePixelRatio || 1, 1);
      const cssWidth = Math.max(320, Math.floor(canvas.clientWidth || 980));
      const cssHeight = 320;
      const reqWidth = Math.floor(cssWidth * dpr);
      const reqHeight = Math.floor(cssHeight * dpr);
      if (canvas.width !== reqWidth || canvas.height !== reqHeight) {
        canvas.width = reqWidth;
        canvas.height = reqHeight;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cssWidth, cssHeight);
      const styles = getComputedStyle(document.body);
      const surface = styles.getPropertyValue('--surface').trim() || '#ffffff';
      const grid = styles.getPropertyValue('--chart-grid').trim() || '#d8dee8';
      const text = styles.getPropertyValue('--text').trim() || '#1f2937';
      const brand = styles.getPropertyValue('--brand').trim() || '#0b4fa3';
      const brandSoft = styles.getPropertyValue('--brand-soft').trim() || '#dbeafe';
      const muted = styles.getPropertyValue('--muted').trim() || '#6b7280';
      const fontFamily = styles.getPropertyValue('--chart-font').trim() || 'sans-serif';
      const padLeft = 56;
      const padRight = 18;
      const padTop = 26;
      const padBottom = 44;
      const w = cssWidth - padLeft - padRight;
      const h = cssHeight - padTop - padBottom;
      const chartBottom = padTop + h;
      ctx.font = `12px ${fontFamily}`;
      ctx.fillStyle = surface;
      ctx.fillRect(0, 0, cssWidth, cssHeight);
      if (!points.length) {
        ctx.fillStyle = muted;
        ctx.fillText('暂无可绘制价格点', padLeft, padTop + 10);
        return;
      }
      const vals = points.map(p => p.value).filter(v => typeof v === 'number');
      if (!vals.length) {
        ctx.fillStyle = muted;
        ctx.fillText('暂无可绘制价格点', padLeft, padTop + 10);
        return;
      }
      let minV = Math.min(...vals);
      let maxV = Math.max(...vals);
      // When all values are identical, add a small vertical range so the line/point is visible.
      if (Math.abs(maxV - minV) < 1e-9) {
        const pad = Math.max(Math.abs(maxV) * 0.05, 1);
        minV -= pad;
        maxV += pad;
      }
      const minTs = Math.min(...points.map((p) => p.ts));
      const maxTs = Math.max(...points.map((p) => p.ts));
      const yTicks = 4;
      ctx.strokeStyle = grid;
      ctx.lineWidth = 1;
      for (let i = 0; i <= yTicks; i++) {
        const y = padTop + (h / yTicks) * i;
        ctx.beginPath();
        ctx.moveTo(padLeft, y);
        ctx.lineTo(padLeft + w, y);
        ctx.stroke();
        const tickValue = maxV - ((maxV - minV) / yTicks) * i;
        ctx.fillStyle = muted;
        ctx.fillText(tickValue.toFixed(2), 8, y + 4);
      }
      ctx.strokeStyle = grid;
      ctx.beginPath();
      ctx.moveTo(padLeft, padTop);
      ctx.lineTo(padLeft, chartBottom);
      ctx.lineTo(padLeft + w, chartBottom);
      ctx.stroke();

      trendPlotPoints = [];
      const linePath = new Path2D();
      const areaPath = new Path2D();
      ctx.beginPath();
      points.forEach((p, idx) => {
        const x = padLeft + ((p.ts - minTs) / Math.max(maxTs - minTs, 1)) * w;
        const y = padTop + (1 - ((p.value - minV) / Math.max(maxV - minV, 1e-9))) * h;
        trendPlotPoints.push({ x, y, p });
        if (idx === 0) {
          linePath.moveTo(x, y);
          areaPath.moveTo(x, chartBottom);
          areaPath.lineTo(x, y);
        } else {
          linePath.lineTo(x, y);
          areaPath.lineTo(x, y);
        }
      });
      const lastPoint = trendPlotPoints[trendPlotPoints.length - 1];
      if (lastPoint) {
        areaPath.lineTo(lastPoint.x, chartBottom);
        areaPath.closePath();
      }

      const fillGradient = ctx.createLinearGradient(0, padTop, 0, chartBottom);
      fillGradient.addColorStop(0, brandSoft);
      fillGradient.addColorStop(1, 'transparent');
      ctx.fillStyle = fillGradient;
      ctx.fill(areaPath);

      ctx.strokeStyle = brand;
      ctx.lineWidth = 2.6;
      ctx.shadowColor = 'rgba(11,79,163,0.22)';
      ctx.shadowBlur = 6;
      ctx.stroke(linePath);
      ctx.shadowBlur = 0;
      // Draw point markers so single-point data is still visible.
      ctx.fillStyle = brand;
      points.forEach((p) => {
        const x = padLeft + ((p.ts - minTs) / Math.max(maxTs - minTs, 1)) * w;
        const y = padTop + (1 - ((p.value - minV) / Math.max(maxV - minV, 1e-9))) * h;
        ctx.beginPath();
        ctx.arc(x, y, 3.1, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.fillStyle = text;
      ctx.font = `600 13px ${fontFamily}`;
      ctx.fillText(title || '', padLeft, 16);
      ctx.font = `12px ${fontFamily}`;
      ctx.fillStyle = muted;
      ctx.fillText(`单位：${unit || 'CNY'}  |  最低 ${minV.toFixed(2)} / 最高 ${maxV.toFixed(2)}`, padLeft + 2, cssHeight - 10);
      if (points.length) {
        const startLabel = points[0].label || '';
        const endLabel = points[points.length - 1].label || '';
        ctx.fillText(startLabel, padLeft, cssHeight - 26);
        const endWidth = ctx.measureText(endLabel).width;
        ctx.fillText(endLabel, padLeft + w - endWidth, cssHeight - 26);
      }
      if (hoverPoint) {
        const hp = hoverPoint;
        ctx.save();
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = muted;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(hp.x, padTop);
        ctx.lineTo(hp.x, chartBottom);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(padLeft, hp.y);
        ctx.lineTo(padLeft + w, hp.y);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = '#ffffff';
        ctx.beginPath();
        ctx.arc(hp.x, hp.y, 6, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = brand;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(hp.x, hp.y, 6, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }
    }

    function renderObservationTable(rows) {
      const body = document.getElementById('obs-body');
      const pageMeta = document.getElementById('obs-page-meta');
      const prevBtn = document.getElementById('obs-prev-btn');
      const nextBtn = document.getElementById('obs-next-btn');
      if (!rows.length) {
        body.innerHTML = '<tr><td colspan="5" class="empty">暂无采集数据</td></tr>';
        pageMeta.textContent = '第 0 条，共 0 条';
        prevBtn.disabled = true;
        nextBtn.disabled = true;
        return;
      }
      body.innerHTML = '';
      const all = rows.slice().reverse();
      const total = all.length;
      const totalPages = Math.max(1, Math.ceil(total / OBS_PAGE_SIZE));
      obsPage = Math.max(1, Math.min(obsPage, totalPages));
      const start = (obsPage - 1) * OBS_PAGE_SIZE;
      const pageRows = all.slice(start, start + OBS_PAGE_SIZE);
      const from = start + 1;
      const to = Math.min(start + OBS_PAGE_SIZE, total);
      pageMeta.textContent = `第 ${obsPage}/${totalPages} 页 · 显示 ${from}-${to} / ${total}`;
      prevBtn.disabled = obsPage <= 1;
      nextBtn.disabled = obsPage >= totalPages;
      for (const r of pageRows) {
        const delta = r.delta_from_prev;
        let deltaText = '-';
        let deltaCls = 'delta-flat';
        if (typeof delta === 'number') {
          if (delta > 0) {
            deltaText = `+${delta.toFixed(2)}`;
            deltaCls = 'delta-up';
          } else if (delta < 0) {
            deltaText = `${delta.toFixed(2)}`;
            deltaCls = 'delta-down';
          } else {
            deltaText = '0.00';
          }
        }
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${r.index ?? '-'}</td>
          <td>${escapeHtml(r.item_name || '-')}</td>
          <td>${escapeHtml(r.captured_at || '-')}</td>
          <td>${typeof r.price === 'number' ? r.price.toFixed(2) : '-'}</td>
          <td class="${deltaCls}">${deltaText}</td>
        `;
        body.appendChild(tr);
      }
    }

    function windowSpanLabel(windowDaysStr) {
      const n = Number(windowDaysStr);
      if (n === 1) return '近1天（24小时）';
      if (n === 3) return '近3天';
      if (Number.isFinite(n) && n > 0) return `近${n}天`;
      return '';
    }

    function filterRowsByWindow(rows, windowDaysStr) {
      const n = Number(windowDaysStr);
      if (!Number.isFinite(n) || n <= 0) return Array.isArray(rows) ? rows : [];
      const cutoff = Date.now() - n * 24 * 60 * 60 * 1000;
      return (rows || []).filter((r) => {
        const ts = Date.parse(r.captured_at || '');
        return Number.isFinite(ts) && ts >= cutoff;
      });
    }

    function inferPriceUnit(keyword, rows) {
      const k = String(keyword || '').toLowerCase();
      if (/usd|xau|xag|wti|brent|btc|eth|\\$/.test(k)) return 'USD';
      if (/eur|欧元/.test(k)) return 'EUR';
      if (/jpy|日元/.test(k)) return 'JPY';
      if (Array.isArray(rows)) {
        for (const r of rows) {
          const c = String(r?.currency || '').toUpperCase();
          if (c) return c;
        }
      }
      return 'CNY';
    }

    function buildPointsFromObservations(rows) {
      const points = [];
      for (const r of rows || []) {
        if (typeof r.price !== 'number' || !r.captured_at) continue;
        const ts = Date.parse(r.captured_at) || 0;
        if (!ts) continue;
        const d = new Date(ts);
        const label = `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
        points.push({ ts, value: r.price, label, rawTime: r.captured_at });
      }
      points.sort((a, b) => a.ts - b.ts);
      return points;
    }

    async function loadDetail() {
      const windowDays = document.getElementById('window-select').value;
      if (!activeMonitorId) {
        drawLine([], '');
        document.getElementById('obs-body').innerHTML = '<tr><td colspan="5" class="empty">暂无可用追踪商品</td></tr>';
        document.getElementById('right-title').textContent = '价格趋势详情';
        return;
      }
      const current = monitors.find((m) => m.monitor_id === activeMonitorId);
      document.getElementById('right-title').textContent = `${current?.keyword || '未命名商品'} 价格趋势`;
      const [tsRes, obsRes] = await Promise.all([
        fetch(`/api/v1/public/monitoring/${activeMonitorId}/timeseries?window_days=${windowDays}`),
        fetch(`/api/v1/public/monitoring/${activeMonitorId}/observations?limit=500`),
      ]);
      if (!tsRes.ok) throw new Error(`timeseries HTTP ${tsRes.status}`);
      if (!obsRes.ok) throw new Error(`observations HTTP ${obsRes.status}`);
      const ts = await tsRes.json();
      const obs = await obsRes.json();
      const obsRows = Array.isArray(obs.rows) ? obs.rows : [];
      const rowsInWindow = filterRowsByWindow(obsRows, windowDays);
      let pts = buildPointsFromObservations(rowsInWindow);
      if (!pts.length && Array.isArray(ts.points) && ts.points.length) {
        pts = ts.points
          .filter((x) => typeof x.avg_price === 'number' && x.date)
          .map((x) => {
            const ts2 = Date.parse(String(x.date) + 'T00:00:00') || 0;
            return { ts: ts2, value: x.avg_price, label: String(x.date).slice(5), rawTime: String(x.date) };
          })
          .sort((a, b) => a.ts - b.ts);
      }
      const spanLabel = windowSpanLabel(windowDays);
      const unit = inferPriceUnit(current?.keyword || '', rowsInWindow);
      lastChartPoints = pts;
      lastChartTitle = `${current?.keyword || ''}${spanLabel ? `（${spanLabel}）` : ''}`;
      lastChartUnit = unit;
      drawLine(lastChartPoints, lastChartTitle, lastChartUnit);
      currentObservationRows = rowsInWindow;
      obsPage = 1;
      renderObservationTable(currentObservationRows);
    }

    function setupChartHover() {
      const canvas = document.getElementById('trend-canvas');
      const tooltip = document.getElementById('chart-tooltip');
      if (!canvas || !tooltip) return;
      canvas.addEventListener('mousemove', (ev) => {
        if (!trendPlotPoints.length) {
          tooltip.style.display = 'none';
          return;
        }
        const rect = canvas.getBoundingClientRect();
        const x = ev.clientX - rect.left;
        const y = ev.clientY - rect.top;
        let nearest = null;
        let minDist = Number.POSITIVE_INFINITY;
        for (const item of trendPlotPoints) {
          const dx = item.x - x;
          const dy = item.y - y;
          const dist = dx * dx + dy * dy;
          if (dist < minDist) {
            minDist = dist;
            nearest = item;
          }
        }
        if (!nearest) {
          tooltip.style.display = 'none';
          return;
        }
        const threshold = 18 * 18;
        if (minDist > threshold) {
          tooltip.style.display = 'none';
          return;
        }
        drawLine(lastChartPoints, lastChartTitle, lastChartUnit, nearest);
        tooltip.innerHTML = `时间：${escapeHtml(nearest.p.rawTime || nearest.p.label || '-')}<br/>价格：${Number(nearest.p.value).toFixed(2)} ${escapeHtml(lastChartUnit || 'CNY')}`;
        tooltip.style.display = 'block';
        tooltip.style.left = `${nearest.x + 16}px`;
        tooltip.style.top = `${Math.max(8, nearest.y - 10)}px`;
      });
      canvas.addEventListener('mouseleave', () => {
        drawLine(lastChartPoints, lastChartTitle, lastChartUnit);
        tooltip.style.display = 'none';
      });
    }

    document.getElementById('refresh-list-btn').addEventListener('click', async () => {
      await loadMonitors();
      await loadDetail();
    });
    document.getElementById('refresh-detail-btn').addEventListener('click', loadDetail);
    document.getElementById('window-select').addEventListener('change', loadDetail);
    document.getElementById('monitor-search').addEventListener('input', renderMonitorList);
    document.getElementById('obs-prev-btn').addEventListener('click', () => {
      obsPage -= 1;
      renderObservationTable(currentObservationRows);
    });
    document.getElementById('obs-next-btn').addEventListener('click', () => {
      obsPage += 1;
      renderObservationTable(currentObservationRows);
    });
    function toggleDarkMode() {
      document.body.classList.toggle('dark');
      localStorage.setItem('oc_dark', document.body.classList.contains('dark') ? '1' : '0');
      loadDetail();
    }
    function setupDarkMode() {
      if (localStorage.getItem('oc_dark') === '1') document.body.classList.add('dark');
    }
    (async () => {
      try {
        setupDarkMode();
        setupChartHover();
        await loadMonitors();
        await loadDetail();
      } catch (e) {
        document.getElementById('obs-body').innerHTML = `<tr><td colspan="5" class="empty">加载失败：${escapeHtml(e?.message || '未知错误')}</td></tr>`;
      }
    })();
  </script>
</body>
</html>
"""
    )


@app.get("/keyword-tracking", summary="监测参数页面")
def keyword_tracking_page() -> HTMLResponse:
    return HTMLResponse(
        """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>监测参数</title>
  <style>
    :root {
      --bg: #f7f8fb; --surface: #ffffff; --surface-2: #f1f3f7; --text: #1f2937;
      --muted: #6b7280; --line: #d8dee8; --brand: #0b4fa3; --header: #0a2f66; --header-text: #ffffff;
    }
    body.dark {
      --bg: #0f1218; --surface: #171c25; --surface-2: #202735; --text: #e6edf7;
      --muted: #9fb0c9; --line: #2c3444; --brand: #66a3ff; --header: #101624; --header-text: #f3f6fd;
    }
    body { margin:0; font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background:var(--bg); color:var(--text); }
    .wrap { width:min(1200px, 100% - 24px); margin:0 auto; }
    .topbar { background:var(--header); color:var(--header-text); border-bottom: 1px solid rgba(255,255,255,0.15); }
    .topbar-inner { display:flex; align-items:center; justify-content:space-between; padding:12px 0; }
    .logo { font-size: 20px; font-weight: 700; letter-spacing: .5px; }
    .top-actions button { border:1px solid rgba(255,255,255,.35); background:rgba(255,255,255,.08); color:var(--header-text); padding:7px 12px; border-radius:12px; cursor:pointer; font-size:14px; }
    .nav { background:var(--surface); border-bottom:1px solid var(--line); }
    .nav ul { list-style:none; margin:0; padding:0; display:flex; gap:18px; overflow-x:auto; white-space:nowrap; }
    .nav li, .nav a { padding:12px 0; border-bottom:2px solid transparent; cursor:pointer; color:inherit; display:inline-block; text-decoration:none; }
    .nav li.active { border-color:var(--brand); color:var(--brand); font-weight:600; }
    h1 { margin:18px 0 8px; color:var(--brand); }
    .muted { color:var(--muted); }
    table { width:100%; border-collapse: collapse; background:var(--surface); border:1px solid var(--line); border-radius:12px; overflow:hidden; margin: 12px 0 24px; }
    th, td { padding:10px; border-bottom:1px solid var(--line); text-align:left; font-size:14px; }
    th { background:var(--surface-2); }
    .ok { color:#127a38; font-weight:700; }
    .warn { color:#9a6700; font-weight:700; }
    .cards { display:grid; gap:14px; margin: 4px 0 20px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
    .card { background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:12px 14px; }
    .card .k { color:var(--muted); font-size:12px; margin-bottom:4px; }
    .card .v { font-size:20px; font-weight:700; color:var(--brand); }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="wrap topbar-inner">
      <div class="logo">OpenClaw市场趋势自动化分析平台</div>
      <div class="top-actions">
        <button onclick="toggleDarkMode()">暗色模式</button>
        <button onclick="location.href='/docs'">接口文档</button>
      </div>
    </div>
  </div>
  <div class="nav">
    <div class="wrap">
      <ul id="category-nav">
        <li><a href="/">门户首页</a></li>
        <li><a href="/?page=news">新闻动态</a></li>
        <li><a href="/price-trend">价格趋势</a></li>
        <li><a href="/topic-analysis">专题分析</a></li>
        <li class="active"><a href="/keyword-tracking">监测参数</a></li>
      </ul>
    </div>
  </div>
  <div class="wrap">
    <h1>监测参数</h1>
    <div class="muted">本页汇总价格监测与新闻监测参数：价格 monitor 覆盖度、URL/观测、最近采样；新闻按关键词聚合条目数与最近发布时间。</div>
    <h2>价格监测任务</h2>
    <table>
      <thead>
        <tr>
          <th>关键词</th>
          <th>monitor_id</th>
          <th>cadence</th>
          <th>URL数</th>
          <th>观测数</th>
          <th>最近采样</th>
          <th>状态</th>
        </tr>
      </thead>
      <tbody id="tbody">
        <tr><td colspan="7" class="muted">加载中...</td></tr>
      </tbody>
    </table>
    <h2>新闻监测任务（按关键词聚合）</h2>
    <table>
      <thead>
        <tr>
          <th>关键词</th>
          <th>新闻条目数</th>
          <th>最近发布时间</th>
          <th>最近入库时间</th>
          <th>状态</th>
        </tr>
      </thead>
      <tbody id="news-tbody">
        <tr><td colspan="5" class="muted">加载中...</td></tr>
      </tbody>
    </table>
    <h2>分析报告生成</h2>
    <div class="cards">
      <div class="card"><div class="k">已发布报告数</div><div id="report-count" class="v">-</div></div>
      <div class="card"><div class="k">最近生成时间</div><div id="report-last-time" class="v" style="font-size:15px;">-</div></div>
      <div class="card"><div class="k">涉及关键词数</div><div id="report-keywords" class="v">-</div></div>
    </div>
    <table>
      <thead>
        <tr>
          <th>关键词</th>
          <th>报告数</th>
          <th>最近生成时间</th>
          <th>状态</th>
        </tr>
      </thead>
      <tbody id="report-tbody">
        <tr><td colspan="4" class="muted">加载中...</td></tr>
      </tbody>
    </table>
  </div>
  <script>
    async function loadMonitors() {
      const body = document.getElementById('tbody');
      try {
        const res = await fetch('/api/v1/public/monitoring/monitors');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const arr = await res.json();
        if (!Array.isArray(arr) || !arr.length) {
          body.innerHTML = '<tr><td colspan="7" class="muted">暂无关键词监测任务。</td></tr>';
          return;
        }
        body.innerHTML = '';
        for (const m of arr) {
          const healthy = (m.url_count || 0) > 0 && (m.observation_count || 0) > 0;
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td>${m.keyword || '-'}</td>
            <td>${m.monitor_id || '-'}</td>
            <td>${m.cadence || '-'}</td>
            <td>${m.url_count || 0}</td>
            <td>${m.observation_count || 0}</td>
            <td>${m.last_captured_at || '-'}</td>
            <td class="${healthy ? 'ok' : 'warn'}">${healthy ? '正常' : '待采样'}</td>
          `;
          body.appendChild(tr);
        }
      } catch (e) {
        body.innerHTML = `<tr><td colspan="7" class="muted">加载失败：${e?.message || '未知错误'}</td></tr>`;
      }
    }
    function _fmtTs(v) {
      return v || '-';
    }
    async function loadNewsMonitoring() {
      const body = document.getElementById('news-tbody');
      try {
        const res = await fetch('/api/v1/public/news/library?limit=500');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const arr = await res.json();
        if (!Array.isArray(arr) || !arr.length) {
          body.innerHTML = '<tr><td colspan="5" class="muted">暂无新闻监测数据。</td></tr>';
          return;
        }
        const grouped = new Map();
        for (const item of arr) {
          const keyword = (item.keyword || '未命名关键词').trim() || '未命名关键词';
          const published = item.published_at || null;
          const created = item.created_at || null;
          if (!grouped.has(keyword)) {
            grouped.set(keyword, { keyword, count: 0, latestPublished: null, latestCreated: null });
          }
          const g = grouped.get(keyword);
          g.count += 1;
          if (published && (!g.latestPublished || published > g.latestPublished)) g.latestPublished = published;
          if (created && (!g.latestCreated || created > g.latestCreated)) g.latestCreated = created;
        }
        const rows = Array.from(grouped.values()).sort((a, b) => {
          const ta = a.latestPublished || a.latestCreated || '';
          const tb = b.latestPublished || b.latestCreated || '';
          return tb.localeCompare(ta);
        });
        body.innerHTML = '';
        for (const n of rows) {
          const healthy = (n.count || 0) > 0;
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td>${n.keyword}</td>
            <td>${n.count || 0}</td>
            <td>${_fmtTs(n.latestPublished)}</td>
            <td>${_fmtTs(n.latestCreated)}</td>
            <td class="${healthy ? 'ok' : 'warn'}">${healthy ? '正常' : '待入库'}</td>
          `;
          body.appendChild(tr);
        }
      } catch (e) {
        body.innerHTML = `<tr><td colspan="5" class="muted">加载失败：${e?.message || '未知错误'}</td></tr>`;
      }
    }
    async function loadReportMonitoring() {
      const body = document.getElementById('report-tbody');
      const countEl = document.getElementById('report-count');
      const lastEl = document.getElementById('report-last-time');
      const kwEl = document.getElementById('report-keywords');
      try {
        const res = await fetch('/api/v1/public/reports');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const arr = await res.json();
        if (!Array.isArray(arr) || !arr.length) {
          countEl.textContent = '0';
          lastEl.textContent = '-';
          kwEl.textContent = '0';
          body.innerHTML = '<tr><td colspan="4" class="muted">暂无已发布分析报告。</td></tr>';
          return;
        }
        countEl.textContent = String(arr.length);
        const grouped = new Map();
        let latest = null;
        for (const item of arr) {
          const keyword = (item.keyword || '未命名关键词').trim() || '未命名关键词';
          const generatedAt = item.generated_at || null;
          if (!grouped.has(keyword)) grouped.set(keyword, { keyword, count: 0, latestGeneratedAt: null });
          const g = grouped.get(keyword);
          g.count += 1;
          if (generatedAt && (!g.latestGeneratedAt || generatedAt > g.latestGeneratedAt)) g.latestGeneratedAt = generatedAt;
          if (generatedAt && (!latest || generatedAt > latest)) latest = generatedAt;
        }
        lastEl.textContent = latest || '-';
        kwEl.textContent = String(grouped.size);
        const rows = Array.from(grouped.values()).sort((a, b) => {
          const ta = a.latestGeneratedAt || '';
          const tb = b.latestGeneratedAt || '';
          return tb.localeCompare(ta);
        });
        body.innerHTML = '';
        for (const r of rows) {
          const healthy = (r.count || 0) > 0;
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td>${r.keyword}</td>
            <td>${r.count || 0}</td>
            <td>${r.latestGeneratedAt || '-'}</td>
            <td class="${healthy ? 'ok' : 'warn'}">${healthy ? '正常' : '待生成'}</td>
          `;
          body.appendChild(tr);
        }
      } catch (e) {
        countEl.textContent = '-';
        lastEl.textContent = '-';
        kwEl.textContent = '-';
        body.innerHTML = `<tr><td colspan="4" class="muted">加载失败：${e?.message || '未知错误'}。如提示 503，请先配置 OPENCLAW_DATABASE_URL。</td></tr>`;
      }
    }
    function toggleDarkMode() {
      document.body.classList.toggle('dark');
      localStorage.setItem('oc_dark', document.body.classList.contains('dark') ? '1' : '0');
    }
    function setupDarkMode() {
      if (localStorage.getItem('oc_dark') === '1') document.body.classList.add('dark');
    }
    setupDarkMode();
    loadMonitors();
    loadNewsMonitoring();
    loadReportMonitoring();
  </script>
</body>
</html>
"""
    )


@app.get("/healthz", summary="健康检查", description="用于检测服务是否存活。")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/healthz/db", summary="数据库健康检查", description="用于检测 PostgreSQL 连通性。")
def healthz_db() -> dict:
    if not settings.database_url:
        return {"ok": False, "enabled": False, "detail": "database_url is not configured"}
    try:
        import psycopg

        with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"ok": True, "enabled": True}
    except Exception as exc:
        return {"ok": False, "enabled": True, "detail": str(exc)}
