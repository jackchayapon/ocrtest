param([switch]$Browser)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskTestTemp = Join-Path $taskRoot ('.runtime\pytest-' + [guid]::NewGuid().ToString('N'))
Push-Location (Join-Path $taskRoot 'backend')
try {
    & .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp $taskTestTemp
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed' }
    & .\.venv\Scripts\python.exe -m ruff check app tests alembic
    if ($LASTEXITCODE -ne 0) { throw 'Backend lint failed' }
} finally { Pop-Location }
Push-Location (Join-Path $taskRoot 'frontend')
try {
    foreach ($taskCheck in @('typecheck', 'lint', 'build')) {
        & npm.cmd run $taskCheck
        if ($LASTEXITCODE -ne 0) { throw "Frontend $taskCheck failed" }
    }
    if ($Browser) {
        & (Join-Path $PSScriptRoot 'e2e.ps1')
    }
} finally { Pop-Location }
