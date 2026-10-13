param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5174,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendRoot = Join-Path $ProjectRoot "backend"
$FrontendRoot = Join-Path $ProjectRoot "frontend"
$LogRoot = Join-Path $ProjectRoot "runtime-logs"

function Test-ListeningPort {
    param([int]$Port)
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Wait-HttpReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 30
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Start-DashboardService {
    param(
        [string]$Name,
        [string]$Executable,
        [string]$WorkingDirectory,
        [string[]]$Arguments,
        [int]$Port,
        [string]$StdoutPath,
        [string]$StderrPath
    )
    if (Test-ListeningPort $Port) {
        Write-Host "$Name is already listening on port $Port; skipping." -ForegroundColor Yellow
        return
    }

    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory -RedirectStandardOutput $StdoutPath `
        -RedirectStandardError $StderrPath -WindowStyle Hidden -PassThru

    Write-Host "$Name started, PID=$($process.Id), port=$Port" -ForegroundColor Green
}

if (-not (Test-Path (Join-Path $BackendRoot "main.py"))) {
    throw "Backend entrypoint not found: $BackendRoot\main.py"
}
if (-not (Test-Path (Join-Path $FrontendRoot "package.json"))) {
    throw "Frontend package not found: $FrontendRoot\package.json"
}

$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
}
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) {
    $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
}
if (-not $pythonCommand) { throw "Python was not found in PATH. Install Python 3.11+ first." }
if (-not $npmCommand) { throw "npm was not found in PATH. Install Node.js 18+ first." }

New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
$backendOut = Join-Path $LogRoot "backend.out.log"
$backendErr = Join-Path $LogRoot "backend.err.log"
$frontendOut = Join-Path $LogRoot "frontend.out.log"
$frontendErr = Join-Path $LogRoot "frontend.err.log"

Start-DashboardService `
    -Name "Backend FastAPI" `
    -Executable $pythonCommand.Source `
    -WorkingDirectory $BackendRoot `
    -Arguments @("-X", "utf8", "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "$BackendPort") `
    -Port $BackendPort `
    -StdoutPath $backendOut `
    -StderrPath $backendErr

Start-DashboardService `
    -Name "Frontend Vite" `
    -Executable $npmCommand.Source `
    -WorkingDirectory $FrontendRoot `
    -Arguments @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$FrontendPort") `
    -Port $FrontendPort `
    -StdoutPath $frontendOut `
    -StderrPath $frontendErr

$backendReady = Wait-HttpReady "http://127.0.0.1:$BackendPort/api/health"
$frontendReady = Wait-HttpReady "http://127.0.0.1:$FrontendPort/"

if (-not $backendReady) {
    Write-Warning "Backend health check failed. See: $backendErr"
}
if (-not $frontendReady) {
    Write-Warning "Frontend health check failed. See: $frontendErr"
}

if ($backendReady -and $frontendReady) {
    $url = "http://127.0.0.1:$FrontendPort/staff"
    Write-Host "Dashboard is ready: $url" -ForegroundColor Cyan
    if ($OpenBrowser) {
        Start-Process $url
    }
    exit 0
}

exit 1
