<#
.SYNOPSIS
    Apply RHEA canonical-store database migrations.
#>
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$env:PYTHONPATH = Join-Path $Root 'backend'
if (-not $env:RHEA_POSTGRES_DSN) {
    # Ask Compose for the published port instead of guessing a free port.
    $composeFile = Join-Path $Root 'infra\docker-compose.yml'
    $published = & docker compose -f $composeFile port postgres 5432 2>$null
    $port = '5432'
    if ($LASTEXITCODE -eq 0 -and $published) {
        if ($published -match ':(\d+)\s*$') { $port = $Matches[1] }
    }
    $env:RHEA_POSTGRES_HOST_PORT = $port
    $env:RHEA_POSTGRES_DSN = "postgresql+psycopg://rhea:rhea-demo@localhost:$port/rhea"
}
$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
& $python -m alembic upgrade head
