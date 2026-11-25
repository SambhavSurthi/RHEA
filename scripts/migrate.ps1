<#
.SYNOPSIS
    Apply RHEA canonical-store database migrations.
#>
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$env:PYTHONPATH = Join-Path $Root 'backend'
if (-not $env:RHEA_POSTGRES_HOST_PORT) {
    $port = 5432
    for ($candidate = 5432; $candidate -le 5482; $candidate++) {
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $task = $client.ConnectAsync('127.0.0.1', $candidate)
            $busy = $task.Wait(300) -and $task.Status -eq 'RanToCompletion'
        } finally { $client.Close() }
        if (-not $busy) { $port = $candidate; break }
    }
    $env:RHEA_POSTGRES_HOST_PORT = "$port"
}
if (-not $env:RHEA_POSTGRES_DSN) {
    $env:RHEA_POSTGRES_DSN = "postgresql+psycopg://rhea:rhea-demo@localhost:$($env:RHEA_POSTGRES_HOST_PORT)/rhea"
}
$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
& $python -m alembic upgrade head
