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
Write-Host "Done. Open:"
Write-Host "  - Home:  http://127.0.0.1:$Port/"
Write-Host "  - Docs:  http://127.0.0.1:$Port/docs"
Write-Host "  - Health:http://127.0.0.1:$Port/healthz"
Write-Host ""
Write-Host "Note: PostgreSQL is not auto-installed/configured by this script."
