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
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f6f8fa; color: #1f2328; }
    .wrap { max-width: 1100px; margin: 0 auto; padding: 24px; }
    .card { background: #fff; border: 1px solid #d0d7de; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
    h1,h2,h3 { margin: 0 0 12px; }
    .muted { color: #57606a; font-size: 14px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    ul { padding-left: 20px; }
    button { border: 1px solid #1f883d; background: #1f883d; color: #fff; border-radius: 6px; padding: 8px 12px; cursor: pointer; }
    button.secondary { border-color: #d0d7de; background: #fff; color: #1f2328; }
    pre { white-space: pre-wrap; background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 12px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>OpenClaw 新闻报告页面</h1>
      <div class="muted">面向用户查看已发布的关键词分析报告</div>
      <div style="margin-top:12px;">
        <button onclick="loadReports()">刷新报告列表</button>
        <button class="secondary" onclick="location.href='/docs'">查看接口文档</button>
      </div>
    </div>
    <div class="grid">
      <div class="card">
        <h2>报告列表</h2>
        <ul id="report-list"></ul>
      </div>
      <div class="card">
        <h2>报告详情</h2>
        <div id="report-detail" class="muted">请先从左侧选择一个报告。</div>
      </div>
    </div>
  </div>
  <script>
    async function loadReports() {
      const res = await fetch('/api/v1/public/reports');
      const data = await res.json();
      const list = document.getElementById('report-list');
      list.innerHTML = '';
      if (!data.length) {
        list.innerHTML = '<li class="muted">暂无报告，请先让 OpenClaw 提交报告。</li>';
        return;
      }
      for (const r of data) {
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.href = '#';
        a.textContent = `${r.title}（${r.keyword}）`;
        a.onclick = async (e) => { e.preventDefault(); await loadDetail(r.ingest_id); };
        li.appendChild(a);
        const span = document.createElement('div');
        span.className = 'muted';
        span.textContent = `生成时间：${r.generated_at}`;
        li.appendChild(span);
        list.appendChild(li);
      }
    }

    async function loadDetail(ingestId) {
      const res = await fetch(`/api/v1/public/reports/${ingestId}`);
      const r = await res.json();
      document.getElementById('report-detail').innerHTML = `
        <h3>${r.title}</h3>
        <div class="muted">关键词：${r.keyword}</div>
        <div class="muted">时间范围：${r.time_range.start} ~ ${r.time_range.end}</div>
        <div class="muted">来源：${(r.sources || []).join(', ')}</div>
        <p>${r.analysis || ''}</p>
        <h4>条目（${r.items_count}）</h4>
        <pre>${JSON.stringify(r.items || [], null, 2)}</pre>
      `;
    }

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
