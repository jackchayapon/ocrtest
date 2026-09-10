$ErrorActionPreference = 'Stop'
if (-not $env:TEST_DATABASE_URL) { throw 'Set TEST_DATABASE_URL to a local PostgreSQL *_test database first.' }
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskLogs = Join-Path $taskRoot '.runtime'
New-Item -ItemType Directory -Force -Path $taskLogs | Out-Null
$taskPython = Join-Path $taskRoot 'backend\.venv\Scripts\python.exe'
$taskNode = (Get-Command node.exe -ErrorAction Stop).Source
$taskOriginal = @{}
foreach ($taskName in @('NEXT_PUBLIC_API_BASE_URL', 'E2E_API_URL', 'E2E_BASE_URL')) {
    $taskOriginal[$taskName] = [Environment]::GetEnvironmentVariable($taskName, 'Process')
}
$taskBackend = $null
$taskFrontend = $null
function Wait-E2EServer($Process, [string]$Url) {
    $taskDeadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $taskDeadline) {
        $Process.Refresh()
        if ($Process.HasExited) { throw "Test server exited; inspect logs in $taskLogs" }
        try {
            $taskResponse = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
            if ($taskResponse.StatusCode -eq 200) { return }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    throw "Test server not ready: $Url"
}
foreach ($taskPort in @(8100, 3100)) {
    $taskSocket = New-Object System.Net.Sockets.TcpClient
    try { $taskSocket.Connect('127.0.0.1', $taskPort) } catch { }
    $taskOccupied = $taskSocket.Connected
    $taskSocket.Dispose()
    if ($taskOccupied) { throw "Test port $taskPort is already occupied." }
}
try {
    $env:NEXT_PUBLIC_API_BASE_URL = 'http://127.0.0.1:8100'
    $env:E2E_API_URL = 'http://127.0.0.1:8100'
    $env:E2E_BASE_URL = 'http://127.0.0.1:3100'
    $taskBackend = Start-Process -FilePath $taskPython -ArgumentList @('-m', 'uvicorn', 'tests.e2e_app:app', '--host', '127.0.0.1', '--port', '8100', '--no-access-log') -WorkingDirectory (Join-Path $taskRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskLogs 'e2e-backend.log') -RedirectStandardError (Join-Path $taskLogs 'e2e-backend-error.log')
    Wait-E2EServer $taskBackend 'http://127.0.0.1:8100/api/health'
    Push-Location (Join-Path $taskRoot 'frontend')
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'E2E production build failed' }
        $taskFrontend = Start-Process -FilePath $taskNode -ArgumentList @('node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', '3100') -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskLogs 'e2e-frontend.log') -RedirectStandardError (Join-Path $taskLogs 'e2e-frontend-error.log')
        Wait-E2EServer $taskFrontend 'http://127.0.0.1:3100'
        & npm.cmd run test:e2e
        if ($LASTEXITCODE -ne 0) { throw 'Playwright failed' }
    } finally { Pop-Location }
} finally {
    foreach ($taskProcess in @($taskFrontend, $taskBackend)) {
        if ($taskProcess -and -not $taskProcess.HasExited) {
            Stop-Process -Id $taskProcess.Id -Force -ErrorAction Stop
        }
    }
    foreach ($taskName in $taskOriginal.Keys) {
        [Environment]::SetEnvironmentVariable($taskName, $taskOriginal[$taskName], 'Process')
    }
}
