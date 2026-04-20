#!/usr/bin/env bash
# After uvicorn is up: call public workflow APIs and print a short Chinese summary.
# Safe to source from other scripts; does not exit the parent shell on API errors.
workflow_post_check() {
  local port="${1:-8000}"
  local base="http://127.0.0.1:${port}"

  echo ""
  echo "==> 工作流就绪检查（Gateway / 一键诊断）"

  python3 - "$base" <<'PY' || true
import json
import sys
import urllib.error
import urllib.request

base = sys.argv[1]

def get_json(path: str):
    url = base + path
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode(errors="replace")
        except Exception:
            body = ""
        return {"_err": f"HTTP {e.code}: {body[:200]}"}
    except Exception as e:
        return {"_err": f"{type(e).__name__}: {e}"}

g = get_json("/api/v1/public/workflow/gateway-status")
if "_err" in g:
    print(f"  Gateway: 检查失败 — {g['_err']}")
else:
    ok = bool(g.get("ok"))
    lat = g.get("latency_ms")
    detail = (g.get("detail") or "-")[:160]
    print(f"  Gateway: {'在线' if ok else '离线'}  latency_ms={lat}  {detail}")

d = get_json("/api/v1/public/workflow/diagnostics")
if "_err" in d:
    print(f"  一键诊断: 请求失败 — {d['_err']}")
else:
    ok = bool(d.get("ok"))
    ec = d.get("error_count", 0)
    wc = d.get("warn_count", 0)
    head = "无阻断错误" if ok else "存在阻断错误"
    print(f"  一键诊断: {head}（error={ec}, warn={wc}）")
    for c in (d.get("checks") or [])[:12]:
        sev = c.get("severity") or "-"
        lab = c.get("label") or "-"
        det = (c.get("detail") or "-")[:140]
        print(f"    [{sev}] {lab}: {det}")
    n = len(d.get("checks") or [])
    if n > 12:
        print(f"    … 共 {n} 项，其余请在网页「工作流管理」或 API 查看")

print("")
print(f"  提示: 网页工作流管理页 — {base}/workflow")
PY
}
