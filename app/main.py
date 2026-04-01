import logging
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.api.v1.openclaw import router as openclaw_router
from app.core.config import settings

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


@app.get("/")
def index() -> HTMLResponse:
    return HTMLResponse(
        """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>OpenClaw 新闻报告门户</title>
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
      padding: 6px 10px;
      border-radius: 4px;
      cursor: pointer;
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
    .nav li {
      padding: 12px 0;
      border-bottom: 2px solid transparent;
      cursor: pointer;
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
      border-radius: 0;
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
    }
    .toolbar button {
      border: 1px solid var(--line);
      background: var(--surface-2);
      color: var(--text);
      padding: 7px 10px;
      cursor: pointer;
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
      <div class="logo">OpenClaw 新闻自动化平台</div>
      <div class="top-actions">
        <button onclick="toggleDarkMode()">暗色模式</button>
        <button onclick="location.href='/docs'">接口文档</button>
      </div>
    </div>
  </div>
  <div class="nav">
    <div class="wrap">
      <ul id="category-nav">
        <li class="active">新闻动态</li>
        <li>专题分析</li>
        <li>价格趋势</li>
        <li>关键词追踪</li>
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
      const src = (md || '').replace(/\r/g, '');
      const lines = src.split('\n');
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
          html += escapeHtml(line) + '\n';
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
        li.onclick = async () => { await loadDetail(r.ingest_id); };
        li.innerHTML = `
          <div class="report-title">${escapeHtml(r.title || '未命名报告')}</div>
          <div class="report-meta">关键词：${escapeHtml(r.keyword || '-')}</div>
          <div class="report-meta">时间：${escapeHtml(r.generated_at || '-')}</div>
        `;
        list.appendChild(li);
      }
    }

    function getFilteredReports() {
      const keyword = document.getElementById('keyword-search').value.trim().toLowerCase();
      if (!keyword) return reportCache;
      return reportCache.filter((r) => (r.keyword || '').toLowerCase().includes(keyword) || (r.title || '').toLowerCase().includes(keyword));
    }

    async function loadReports() {
      const res = await fetch('/api/v1/public/reports');
      const data = await res.json();
      reportCache = data;
      const filtered = getFilteredReports();
      renderReportList(filtered);
      if (filtered.length && !activeIngestId) {
        await loadDetail(filtered[0].ingest_id);
      }
    }

    async function loadDetail(ingestId) {
      const res = await fetch(`/api/v1/public/reports/${ingestId}`);
      const r = await res.json();
      activeIngestId = ingestId;
      renderReportList(getFilteredReports());
      const md = reportToMarkdown(r);
      document.getElementById('report-detail').innerHTML = markdownToHtml(md);
    }

    document.getElementById('keyword-search').addEventListener('input', () => {
      renderReportList(getFilteredReports());
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


@app.get("/api/v1/public/reports", summary="用户侧报告列表")
def list_reports() -> list[dict]:
    root = _rendered_root()
    if not root.exists():
        return []
    reports: list[dict] = []
    for file in sorted(root.glob("*.json"), reverse=True):
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
            reports.append(
                {
                    "ingest_id": payload.get("ingest_id"),
                    "title": payload.get("title"),
                    "keyword": payload.get("keyword"),
                    "generated_at": payload.get("generated_at"),
                }
            )
        except Exception:
            continue
    return reports


@app.get("/api/v1/public/reports/{ingest_id}", summary="用户侧报告详情")
def get_report_detail(ingest_id: str) -> dict:
    target = _rendered_root() / f"{ingest_id}.json"
    if not target.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return json.loads(target.read_text(encoding="utf-8"))


@app.get("/healthz", summary="健康检查", description="用于检测服务是否存活。")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
