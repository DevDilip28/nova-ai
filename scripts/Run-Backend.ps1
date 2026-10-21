$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backend = Join-Path $root 'backend'
Set-Location $backend
& (Join-Path $backend '.venv\Scripts\python.exe') 'run_backend.py'
