<#
.SYNOPSIS
    Run the deterministic test suite and linter from the repository root.
#>
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$env:PYTHONPATH = Join-Path $Root 'backend'
$python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { $python = 'python' }

Write-Host '==> pytest' -ForegroundColor Cyan
& $python -m pytest
Write-Host '==> ruff' -ForegroundColor Cyan
& $python -m ruff check backend/rhea backend/tests frontend/streamlit_app.py
