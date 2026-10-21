param([switch]$InstallDependencies)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backend = Join-Path $root 'backend'
$venv = Join-Path $backend '.venv'
$python = Join-Path $venv 'Scripts\python.exe'

try {
    $py = Get-Command python -ErrorAction Stop
    $version = & $py.Source --version 2>&1
    if ($version -notmatch 'Python 3\.(1[1-9]|[2-9][0-9])') { throw "Python 3.11 or newer is required. Found: $version" }
    $node = Get-Command node -ErrorAction Stop
    $nodeVersion = & $node.Source --version
    if ($nodeVersion -notmatch '^v(2[0-9]|[3-9][0-9])\.') { throw "Node.js 20 or newer is required. Found: $nodeVersion" }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Node.js npm was not found. Install the current Node.js LTS release.' }
    if (-not (Test-Path $venv)) { & $py.Source -m venv $venv }
    if ($InstallDependencies) {
        & $python -m pip install --upgrade pip
        & $python -m pip install -r (Join-Path $backend 'requirements.txt')
        Push-Location $root
        try { & npm install } finally { Pop-Location }
    } elseif (-not (Test-Path (Join-Path $venv 'Scripts\uvicorn.exe')) -or -not (Test-Path (Join-Path $root 'node_modules'))) {
        throw 'Dependencies are missing. Run .\scripts\Start-NOVA.ps1 -InstallDependencies once.'
    }
    if (-not (Test-Path (Join-Path $root '.env'))) { Copy-Item (Join-Path $root '.env.example') (Join-Path $root '.env') }
    $backendScript = Join-Path $PSScriptRoot 'Run-Backend.ps1'
    $mcpScript = Join-Path $PSScriptRoot 'Run-MCP.ps1'
    Start-Process powershell.exe -ArgumentList @('-NoExit','-ExecutionPolicy','Bypass','-File',"`"$backendScript`"") -WorkingDirectory $root
    Start-Process powershell.exe -ArgumentList @('-NoExit','-ExecutionPolicy','Bypass','-File',"`"$mcpScript`"") -WorkingDirectory $root
    Start-Process powershell.exe -ArgumentList @('-NoExit','-Command',"Set-Location -LiteralPath '$root'; npm run dev") -WorkingDirectory $root
    Write-Host "NOVA is starting with Node $nodeVersion. Frontend: http://127.0.0.1:5173  Backend: http://127.0.0.1:8000  MCP: http://127.0.0.1:8001/mcp"
    $envFile = Join-Path $root '.env'
    $providerLine = Select-String -Path $envFile -Pattern '^AI_PROVIDER=' | Select-Object -First 1
    $provider = if ($providerLine) { ($providerLine.Line -split '=', 2)[1].Trim().Trim('"').ToLowerInvariant() } else { 'groq' }
    if ($provider -eq 'groq') {
        if (-not (Select-String -Path $envFile -Pattern '^GROQ_API_KEY=\S+' -Quiet)) { Write-Warning 'Groq API key is missing. Set GROQ_API_KEY in .env.' }
        if (-not (Select-String -Path $envFile -Pattern '^GROQ_MODEL=\S+' -Quiet)) { Write-Warning 'Groq model is missing. Set GROQ_MODEL in .env.' }
    } elseif ($provider -eq 'bedrock') {
        if (-not (Select-String -Path $envFile -Pattern '^BEDROCK_MODEL_ID=\S+' -Quiet)) { Write-Warning 'Bedrock is selected but not configured. Add BEDROCK_MODEL_ID and configure AWS credentials.' }
    } else {
        Write-Warning 'AI_PROVIDER must be groq or bedrock.'
    }
    if (-not (Select-String -Path (Join-Path $root '.env') -Pattern '^TAVILY_API_KEY=\S+' -Quiet)) { Write-Warning 'TAVILY_API_KEY is missing. NOVA will use DuckDuckGo HTML search as its live search fallback.' }
} catch {
    Write-Error "NOVA startup stopped: $($_.Exception.Message)"
    exit 1
}
