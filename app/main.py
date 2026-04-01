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
  <title>OpenClaw 新闻报告</title>
  <style>
    :root {
      --bg: #f4f7fb;
      --card: #ffffff;
      --text: #1f2937;
      --muted: #6b7280;
      --brand: #2563eb;
      --brand-soft: #dbeafe;
      --border: #e5e7eb;
      --shadow: 0 10px 30px rgba(37, 99, 235, 0.10);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background: radial-gradient(circle at 0% 0%, #e7f0ff 0, transparent 30%), var(--bg);
    }
    .wrap { max-width: 1160px; margin: 0 auto; padding: 28px 20px 40px; }
    .hero {
      background: linear-gradient(135deg, #1d4ed8, #2563eb 55%, #3b82f6);
      color: #fff;
      border-radius: 18px;
      padding: 24px;
      box-shadow: var(--shadow);
      margin-bottom: 18px;
    }
    .hero h1 { margin: 0 0 10px; font-size: 30px; }
    .hero p { margin: 0; opacity: .95; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
    .toolbar input {
      background: #ffffff;
      border: 1px solid rgba(255,255,255,.45);
      border-radius: 10px;
      padding: 10px 12px;
      min-width: 260px;
      outline: none;
    }
    .toolbar button {
      border: 0;
      background: #0f172a;
      color: #fff;
      border-radius: 10px;
      padding: 10px 14px;
      cursor: pointer;
      transition: transform .12s ease, opacity .12s ease;
    }
    .toolbar button:hover { transform: translateY(-1px); opacity: .96; }
    .toolbar button.secondary { background: rgba(255,255,255,.2); border: 1px solid rgba(255,255,255,.35); }
    .grid { display: grid; grid-template-columns: 1.05fr 1.2fr; gap: 16px; }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04);
      min-height: 420px;
    }
    .section-title { margin: 0 0 12px; font-size: 20px; }
    .muted { color: var(--muted); font-size: 14px; }
    #report-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
    .report-item {
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px;
      background: #fff;
      transition: border-color .12s ease, box-shadow .12s ease, transform .12s ease;
      cursor: pointer;
    }
    .report-item:hover {
      border-color: #93c5fd;
      box-shadow: 0 8px 20px rgba(59, 130, 246, .12);
      transform: translateY(-1px);
    }
    .report-item.active { background: var(--brand-soft); border-color: #60a5fa; }
    .report-title { font-weight: 600; line-height: 1.4; margin-bottom: 4px; }
    .badge {
      display: inline-block;
      background: #eff6ff;
      color: #1e40af;
      border: 1px solid #bfdbfe;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      margin-right: 6px;
    }
    .detail-header { margin-bottom: 10px; }
    .detail-title { margin: 0 0 6px; font-size: 22px; line-height: 1.35; }
    .meta-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
    .meta-chip {
      background: #f8fafc;
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 5px 10px;
      font-size: 12px;
      color: #334155;
    }
    .analysis {
      background: #f8fafc;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px;
      line-height: 1.7;
      margin: 0 0 12px;
    }
    pre {
      white-space: pre-wrap;
      background: #0b1020;
      color: #dbeafe;
      border-radius: 10px;
      padding: 12px;
      max-height: 280px;
      overflow: auto;
      margin: 0;
    }
    @media (max-width: 920px) {
      .grid { grid-template-columns: 1fr; }
      .card { min-height: auto; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>OpenClaw 新闻报告中心</h1>
      <p>面向业务用户查看关键词趋势分析结果，支持即时刷新与详情浏览。</p>
      <div class="toolbar">
        <input id="keyword-search" placeholder="输入关键词筛选（如：羽毛球）" />
        <button onclick="loadReports()">刷新报告</button>
        <button class="secondary" onclick="location.href='/docs'">接口文档</button>
      </div>
    </div>
    <div class="grid">
      <div class="card">
        <h2 class="section-title">报告列表</h2>
        <ul id="report-list"></ul>
      </div>
      <div class="card">
        <h2 class="section-title">报告详情</h2>
        <div id="report-detail" class="muted">请先从左侧选择一个报告。</div>
      </div>
    </div>
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

    function renderReportList(data) {
      const list = document.getElementById('report-list');
      list.innerHTML = '';
      if (!data.length) {
        list.innerHTML = '<li class="muted">暂无报告，请先让 OpenClaw 提交报告。</li>';
        return;
      }
      for (const r of data) {
        const li = document.createElement('li');
        li.className = 'report-item' + (activeIngestId === r.ingest_id ? ' active' : '');
        li.onclick = async () => { await loadDetail(r.ingest_id); };
        li.innerHTML = `
          <div class="report-title">${escapeHtml(r.title || '未命名报告')}</div>
          <div>
            <span class="badge">${escapeHtml(r.keyword || '未分类')}</span>
            <span class="muted">生成时间：${escapeHtml(r.generated_at || '-')}</span>
          </div>
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
      document.getElementById('report-detail').innerHTML = `
        <div class="detail-header">
          <h3 class="detail-title">${escapeHtml(r.title || '未命名报告')}</h3>
          <div class="meta-row">
            <span class="meta-chip">关键词：${escapeHtml(r.keyword || '-')}</span>
            <span class="meta-chip">条目数：${escapeHtml(r.items_count || 0)}</span>
            <span class="meta-chip">生成时间：${escapeHtml(r.generated_at || '-')}</span>
          </div>
          <div class="muted">时间范围：${escapeHtml(r.time_range?.start || '-')} ~ ${escapeHtml(r.time_range?.end || '-')}</div>
          <div class="muted">来源：${escapeHtml((r.sources || []).join(', ') || '-')}</div>
        </div>
        <p class="analysis">${escapeHtml(r.analysis || '暂无分析内容')}</p>
        <h4>结构化条目 JSON</h4>
        <pre>${escapeHtml(JSON.stringify(r.items || [], null, 2))}</pre>
      `;
    }

    document.getElementById('keyword-search').addEventListener('input', () => {
      renderReportList(getFilteredReports());
    });

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
