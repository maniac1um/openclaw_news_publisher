import logging
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.api.v1.openclaw import router as openclaw_router
from app.core.config import settings
from app.services.report_management_service import ReportManagementService

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


class BulkDeleteRequest(BaseModel):
    ingest_ids: list[str]


@app.get("/")
def index(page: str | None = None) -> HTMLResponse:
    # `/?page=news` keeps the original "news dashboard" UI reachable.
    if page != "news":
        return HTMLResponse(
            """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>OpenClaw 门户首页</title>
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
      display: grid;
      grid-template-columns: 1.05fr 1fr;
      gap: 14px;
      align-items: start;
      padding-bottom: 26px;
    }
    @media (max-width: 920px) {
      .cards { grid-template-columns: 1fr; }
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

    #status-list { list-style: none; padding: 0; margin: 10px 0 0; }
    .status-item {
      padding: 10px 12px;
      border: 1px dashed var(--line);
      border-radius: 14px;
      margin-bottom: 10px;
      background: var(--surface);
    }
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
        <li class="active"><a href="/">门户首页</a></li>
        <li><a href="/?page=news">新闻动态</a></li>
        <li><a href="/topic-analysis">专题分析</a></li>
        <li><a href="/price-trend">价格趋势</a></li>
        <li><a href="/keyword-tracking">关键词追踪</a></li>
      </ul>
    </div>
  </div>

  <div class="wrap">
    <div class="portal-hero">
      <h1>OpenClaw 门户首页</h1>
      <p>选择一个模块进入页面；也可以在下方向 OpenClaw 发送消息（当前仅做前端演示，对后端未实现）。</p>
    </div>

    <div class="cards">
      <div class="card">
        <div class="card-title">向 OpenClaw 发送消息</div>
        <textarea id="openclaw-input" placeholder="输入你希望 OpenClaw 处理的文本（例如：分析某关键词、时间范围或请求的格式）。"></textarea>
        <div class="card-actions">
          <button class="btn primary" id="send-btn">发送</button>
          <button class="btn" onclick="document.getElementById('openclaw-input').value = '';">清空</button>
        </div>
      </div>

      <div class="card">
        <div class="card-title">OpenClaw 工作情况</div>
        <div class="muted" id="status-summary">加载中...</div>
        <ul id="status-list"></ul>
      </div>
    </div>
  </div>

  <div class="portal-footer">
    <div>作者：maniac1um</div>
    <div style="margin-top:6px;"><a href="mailto:maniac1um@163.com">联系作者</a></div>
  </div>

  <div id="send-modal" class="modal-overlay">
    <div class="modal">
      <div class="modal-title">消息已发送</div>
      <div class="modal-body" id="modal-body"></div>
      <div class="modal-actions">
        <button class="btn" onclick="closeModal()">关闭</button>
      </div>
    </div>
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
    function openModal(body) {
      document.getElementById('modal-body').textContent = body;
      document.getElementById('send-modal').style.display = 'flex';
    }
    function closeModal() {
      document.getElementById('send-modal').style.display = 'none';
    }

    async function loadStatus() {
      const summary = document.getElementById('status-summary');
      const list = document.getElementById('status-list');
      summary.textContent = '加载中...';
      list.innerHTML = '';
      try {
        const res = await fetch('/api/v1/public/reports');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const arr = Array.isArray(data) ? data : [];
        summary.textContent = `当前已发布报告：${arr.length} 条`;
        const top = arr.slice(0, 4);
        if (!top.length) {
          const li = document.createElement('li');
          li.className = 'status-item';
          li.innerHTML = `<div class="status-item-title">暂无报告</div><div class="status-item-meta">等待 OpenClaw 提交分析结果...</div>`;
          list.appendChild(li);
          return;
        }
        for (const r of top) {
          const li = document.createElement('li');
          li.className = 'status-item';
          const title = r.title || '未命名报告';
          const meta = r.generated_at || '-';
          li.innerHTML = `<div class="status-item-title">${title}</div><div class="status-item-meta">生成时间：${meta}</div>`;
          list.appendChild(li);
        }
      } catch (err) {
        summary.textContent = '加载失败';
        const li = document.createElement('li');
        li.className = 'status-item';
        li.innerHTML = `<div class="status-item-title">无法获取工作情况</div><div class="status-item-meta">${err?.message || '未知错误'}</div>`;
        list.appendChild(li);
      }
    }

    document.getElementById('send-btn').addEventListener('click', () => {
      const input = document.getElementById('openclaw-input').value.trim();
      if (!input) {
        openModal('你还没有输入消息。');
        return;
      }
      openModal(`你输入的消息：\n${input}\n\n当前仅演示前端对话框，后端发送接口待实现。`);
    });

    // Click outside modal to close.
    document.getElementById('send-modal').addEventListener('click', (e) => {
      if (e.target && e.target.id === 'send-modal') closeModal();
    });

    setupDarkMode();
    loadStatus();
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
        <li><a href="/">门户首页</a></li>
        <li class="active"><a href="/?page=news">新闻动态</a></li>
        <li><a href="/topic-analysis">专题分析</a></li>
        <li><a href="/price-trend">价格趋势</a></li>
        <li><a href="/keyword-tracking">关键词追踪</a></li>
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
        if (filtered.length && !activeIngestId) {
          await loadDetail(filtered[0].ingest_id);
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


def _report_mgmt() -> ReportManagementService:
    return ReportManagementService(raw_root=_raw_root(), rendered_root=_rendered_root())


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
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["report_markdown"] = _report_to_markdown(payload)
    return payload


@app.post("/api/v1/public/reports/bulk-delete", summary="批量删除报告")
def bulk_delete_reports(request: BulkDeleteRequest) -> dict:
    return _report_mgmt().delete_reports(request.ingest_ids)


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
        <li{ ' class="active"' if active_nav_key == "home" else ""}><a href="/">门户首页</a></li>
        <li{ ' class="active"' if active_nav_key == "news" else ""}><a href="/?page=news">新闻动态</a></li>
        <li{ ' class="active"' if active_nav_key == "topic" else ""}><a href="/topic-analysis">专题分析</a></li>
        <li{ ' class="active"' if active_nav_key == "price" else ""}><a href="/price-trend">价格趋势</a></li>
        <li{ ' class="active"' if active_nav_key == "keyword" else ""}><a href="/keyword-tracking">关键词追踪</a></li>
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
    return _coming_soon_page("专题分析", active_nav_key="topic")


@app.get("/price-trend", summary="价格趋势页面")
def price_trend_page() -> HTMLResponse:
    return _coming_soon_page("价格趋势", active_nav_key="price")


@app.get("/keyword-tracking", summary="关键词追踪页面")
def keyword_tracking_page() -> HTMLResponse:
    return _coming_soon_page("关键词追踪", active_nav_key="keyword")


@app.get("/healthz", summary="健康检查", description="用于检测服务是否存活。")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
