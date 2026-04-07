$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $root)))
$pythonCandidates = @()

if ($env:AI_MANGA_FACTORY_PYTHON) {
    $pythonCandidates += $env:AI_MANGA_FACTORY_PYTHON
}

$pythonCandidates += (Join-Path $workspaceRoot ".venvs\ai-manga-factory\Scripts\python.exe")
$pythonCandidates += (Join-Path $root ".venv\Scripts\python.exe")

$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $python) {
    Write-Error "Python executable not found. Expected E:\work\.venvs\ai-manga-factory\Scripts\python.exe or AI_MANGA_FACTORY_PYTHON."
}

Set-Location $root
& $python "$root\start_project.py" backend @args
