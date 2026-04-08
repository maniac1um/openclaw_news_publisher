import logging
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.api.v1.openclaw import router as openclaw_router
from app.api.v1.chat import router as chat_router
from app.core.config import settings
from app.services.monitoring_scheduler import MonitoringScheduler
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
    _monitoring_scheduler = MonitoringScheduler(
        database_url=settings.monitoring_database_url,
        monitor_id=settings.monitoring_scheduler_monitor_id,
        interval_minutes=settings.monitoring_scheduler_interval_minutes,
        run_on_start=settings.monitoring_scheduler_run_on_start,
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
      <p>选择一个模块进入页面；也可以在下方向 OpenClaw 发送消息。</p>
    </div>

    <div class="cards">
      <div class="card chat-card">
        <div class="card-title">OpenClaw 对话</div>
        <div class="chat-session-bar">
          <select id="chat-session-select"></select>
          <button class="btn" id="chat-new-session-btn" type="button">新建会话</button>
          <button class="btn danger" id="chat-delete-session-btn" type="button">删除</button>
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
        <ul id="status-list"></ul>
      </div>

      <div class="card scheduler-card">
        <div class="card-title">定时任务状态</div>
        <div class="muted" id="scheduler-summary">加载中...</div>
        <ul id="scheduler-list"></ul>
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
          const body = document.createElement('div');
          body.className = 'status-item-body';
          const t = document.createElement('div');
          t.className = 'status-item-title';
          t.textContent = '暂无报告';
          const m = document.createElement('div');
          m.className = 'status-item-meta';
          m.textContent = '等待 OpenClaw 提交分析结果...';
          body.appendChild(t);
          body.appendChild(m);
          li.appendChild(body);
          list.appendChild(li);
          return;
        }
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
      } catch (err) {
        summary.textContent = '加载失败';
        const li = document.createElement('li');
        li.className = 'status-item';
        li.innerHTML = `<div class="status-item-title">无法获取工作情况</div><div class="status-item-meta">${err?.message || '未知错误'}</div>`;
        list.appendChild(li);
      }
    }

    async function loadSchedulerStatus() {
      const summary = document.getElementById('scheduler-summary');
      const list = document.getElementById('scheduler-list');
      if (!summary || !list) return;
      summary.textContent = '加载中...';
      list.innerHTML = '';
      try {
        const res = await fetch('/api/v1/public/monitoring/scheduler-status');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const enabled = !!data.enabled;
        const started = !!data.started;
        const configured = !!data.configured;
        const statusText = started ? '运行中' : (enabled ? '未启动' : '已关闭');
        summary.textContent = `内部调度器：${statusText}`;

        const rows = [
          ['模式', data.mode || 'internal'],
          ['是否启用', enabled ? '是' : '否'],
          ['是否已启动', started ? '是' : '否'],
          ['配置完整', configured ? '是' : '否'],
          ['监测任务ID', data.monitor_id || '-'],
          ['执行间隔(分钟)', String(data.interval_minutes ?? '-')],
          ['启动即执行', data.run_on_start ? '是' : '否'],
        ];
        for (const [k, v] of rows) {
          const li = document.createElement('li');
          li.className = 'status-item';
          const body = document.createElement('div');
          body.className = 'status-item-body';
          const t = document.createElement('div');
          t.className = 'status-item-title';
          t.textContent = k;
          const m = document.createElement('div');
          m.className = 'status-item-meta';
          m.textContent = v;
          body.appendChild(t);
          body.appendChild(m);
          li.appendChild(body);
          list.appendChild(li);
        }
      } catch (err) {
        summary.textContent = '加载失败';
        const li = document.createElement('li');
        li.className = 'status-item';
        li.innerHTML = `<div class="status-item-body"><div class="status-item-title">无法获取定时任务状态</div><div class="status-item-meta">${err?.message || '未知错误'}</div></div>`;
        list.appendChild(li);
      }
    }

    const chatMessages = document.getElementById('chat-messages');
    const chatInput = document.getElementById('openclaw-chat-input');
    const chatSendBtn = document.getElementById('chat-send-btn');

    const chatSessionSelect = document.getElementById('chat-session-select');
    const chatNewSessionBtn = document.getElementById('chat-new-session-btn');
    const chatDeleteSessionBtn = document.getElementById('chat-delete-session-btn');

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
      rebuildSessionSelect();
      renderActiveChat();
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
      session.assistantIndex = session.messages.length - 1;

      renderActiveChat();

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

    createSession();
    connectChatWs();

    setupDarkMode();
    loadStatus();
    loadSchedulerStatus();
    setInterval(loadSchedulerStatus, 15000);
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
          if (url.searchParams.get('page') === 'news') {
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


@app.get("/api/v1/public/monitoring/scheduler-status", summary="用户侧定时任务状态")
def public_monitoring_scheduler_status() -> dict:
    return _monitoring_scheduler_status_public(app)


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
