# One-click bootstrap for Windows (PowerShell 5.1+/7+).
# It prepares Python env, installs dependencies, and starts the service.
# It does NOT install/configure PostgreSQL.

[CmdletBinding()]
param(
    [string]$PythonExe = "python",
    [string]$HostBind = "0.0.0.0",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

Write-Host "==> OpenClaw one-click bootstrap (Windows)"
Write-Host "==> Project root: $Root"

if (-not (Get-Command $PythonExe -ErrorAction SilentlyContinue)) {
    throw "Python not found. Install Python 3.11+ first."
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git not found. Install git first."
}

if (-not (Test-Path ".venv")) {
    Write-Host "==> Creating .venv"
    & $PythonExe -m venv .venv
}

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment python not found: $VenvPython"
}

Write-Host "==> Installing dependencies"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e .

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "==> Created .env from .env.example"
    } else {
@"
OPENCLAW_OPENCLAW_API_KEY=dev-openclaw-key
OPENCLAW_OPENCLAW_WS_URL=ws://localhost:18789/ws
OPENCLAW_OPENCLAW_GATEWAY_PROBE_TIMEOUT_SECONDS=2.0
# OPENCLAW_DATABASE_URL=postgresql://openclaw_app:密码@127.0.0.1:5432/openclaw_app
# OPENCLAW_MONITORING_DATABASE_URL=postgresql://openclaw_monitor:密码@127.0.0.1:5432/openclaw_monitor
# OPENCLAW_NEWS_DATABASE_URL=postgresql://openclaw_news:密码@127.0.0.1:5432/openclaw_news
"@ | Out-File -Encoding UTF8 ".env"
        Write-Host "==> Created minimal .env"
    }
}

$PidFile = Join-Path $env:TEMP "openclaw_news_publisher.uvicorn.pid"
$LogFile = Join-Path $env:TEMP "openclaw_news_publisher.server.log"

# Try stopping process from pid file if present
if (Test-Path $PidFile) {
    try {
        $PidText = (Get-Content $PidFile -Raw).Trim()
        if ($PidText) {
            $Proc = Get-Process -Id ([int]$PidText) -ErrorAction SilentlyContinue
            if ($Proc) { Stop-Process -Id $Proc.Id -Force }
        }
    } catch {}
    Remove-Item $PidFile -ErrorAction SilentlyContinue
}

Write-Host "==> Starting server"
$StartInfo = @{
    FilePath = $VenvPython
    ArgumentList = @("-m", "uvicorn", "app.main:app", "--host", $HostBind, "--port", "$Port", "--reload")
    RedirectStandardOutput = $LogFile
    RedirectStandardError = $LogFile
    WindowStyle = "Hidden"
    PassThru = $true
}
$Proc = Start-Process @StartInfo
$Proc.Id | Out-File -Encoding ascii $PidFile

Start-Sleep -Seconds 2
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/healthz" -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) {
        Write-Host "Health check OK: http://127.0.0.1:$Port/healthz"
    } else {
        Write-Warning "Health check returned $($r.StatusCode). Check log: $LogFile"
    }
} catch {
    Write-Warning "Health check failed. Check log: $LogFile"
}

Write-Host ""
Write-Host "==> 工作流就绪检查（Gateway / 一键诊断）"
$wfBase = "http://127.0.0.1:$Port"
try {
    $g = Invoke-RestMethod -Uri "$wfBase/api/v1/public/workflow/gateway-status" -TimeoutSec 10
    $gOk = [bool]$g.ok
    $gLat = $g.latency_ms
    $gDet = "-"
    if ($null -ne $g.detail -and "$($g.detail)" -ne "") {
        $s = "$($g.detail)"
        $gDet = $s.Substring(0, [Math]::Min(160, $s.Length))
    }
    if ($gOk) { Write-Host "  Gateway: 在线  latency_ms=$gLat  $gDet" } else { Write-Host "  Gateway: 离线  latency_ms=$gLat  $gDet" }
} catch {
    Write-Host "  Gateway: 检查失败 — $_"
}
try {
    $d = Invoke-RestMethod -Uri "$wfBase/api/v1/public/workflow/diagnostics" -TimeoutSec 15
    $dOk = [bool]$d.ok
    $ec = $d.error_count
    $wc = $d.warn_count
    $head = if ($dOk) { "无阻断错误" } else { "存在阻断错误" }
    Write-Host "  一键诊断: $head（error=$ec, warn=$wc）"
    $checks = @($d.checks)
    $max = [Math]::Min(12, $checks.Count)
    for ($i = 0; $i -lt $max; $i++) {
        $c = $checks[$i]
        $sev = $c.severity
        $lab = $c.label
        $det = "-"
        if ($null -ne $c.detail -and "$($c.detail)" -ne "") {
            $ds = "$($c.detail)"
            $det = $ds.Substring(0, [Math]::Min(140, $ds.Length))
        }
        Write-Host ("    [{0}] {1}: {2}" -f $sev, $lab, $det)
    }
    if ($checks.Count -gt 12) {
        Write-Host "    … 共 $($checks.Count) 项，其余请在网页「工作流管理」或 API 查看"
    }
} catch {
    Write-Host "  一键诊断: 请求失败 — $_"
}
Write-Host "  提示: 网页工作流管理页 — $wfBase/workflow"

Write-Host ""
Write-Host "Done. Open:"
Write-Host "  - Home:     http://127.0.0.1:$Port/"
Write-Host "  - Workflow: http://127.0.0.1:$Port/workflow"
Write-Host "  - Docs:     http://127.0.0.1:$Port/docs"
Write-Host "  - Health:   http://127.0.0.1:$Port/healthz"
Write-Host ""
Write-Host "Note: PostgreSQL is not auto-installed/configured by this script."
