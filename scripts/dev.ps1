$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskLogs = Join-Path $taskRoot '.runtime'
New-Item -ItemType Directory -Force -Path $taskLogs | Out-Null
$taskPython = Join-Path $taskRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Install backend dependencies first; see README.md.' }
$taskNode = (Get-Command node.exe -ErrorAction Stop).Source
if (-not (Test-Path -LiteralPath (Join-Path $taskRoot 'frontend\node_modules\next\dist\bin\next'))) {
    throw 'Install frontend dependencies first with npm.cmd ci in frontend; see README.md.'
}
foreach ($taskPort in @(8000, 3000)) {
    $taskSocket = New-Object System.Net.Sockets.TcpClient
    try { $taskSocket.Connect('127.0.0.1', $taskPort) } catch { }
    $taskOccupied = $taskSocket.Connected
    $taskSocket.Dispose()
    if ($taskOccupied) {
        throw "Port $taskPort is already in use. Stop the existing development server or reuse it."
    }
}
function Wait-TaskServer($Process, [string]$Url, [string]$Name) {
    $taskDeadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $taskDeadline) {
        $Process.Refresh()
        if ($Process.HasExited) { throw "$Name exited during startup. See $taskLogs." }
        try {
            $taskResponse = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($taskResponse.StatusCode -eq 200) { return }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    throw "$Name did not become ready within 90 seconds. See $taskLogs."
}

$taskBackend = $null
$taskFrontend = $null
try {
    $taskBackend = Start-Process -FilePath $taskPython -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--no-access-log') -WorkingDirectory (Join-Path $taskRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskLogs 'backend.log') -RedirectStandardError (Join-Path $taskLogs 'backend-error.log')
    Wait-TaskServer $taskBackend 'http://127.0.0.1:8000/api/health' 'Backend'
    $taskFrontend = Start-Process -FilePath $taskNode -ArgumentList @('node_modules/next/dist/bin/next', 'dev', '--hostname', '127.0.0.1', '--port', '3000') -WorkingDirectory (Join-Path $taskRoot 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskLogs 'frontend.log') -RedirectStandardError (Join-Path $taskLogs 'frontend-error.log')
    Wait-TaskServer $taskFrontend 'http://127.0.0.1:3000' 'Frontend'
} catch {
    foreach ($taskProcess in @($taskFrontend, $taskBackend)) {
        if ($taskProcess -and -not $taskProcess.HasExited) {
            # Kill only processes created by this invocation, including Next's worker.
            & taskkill.exe /PID $taskProcess.Id /T /F | Out-Null
        }
    }
    throw
}
Write-Output "Backend PID $($taskBackend.Id), frontend PID $($taskFrontend.Id)."
Write-Output "Open http://127.0.0.1:3000. Logs: $taskLogs"
Write-Output 'These are development servers. Stop the printed PIDs when finished.'
