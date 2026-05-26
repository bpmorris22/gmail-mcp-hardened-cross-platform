# Gmail Multi-Account MCP - first-time setup (Windows / PowerShell)
# Run once from this directory:
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
# Or from an existing PowerShell session:
#   .\setup.ps1

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "=== Gmail Multi-Account MCP Setup (Windows) ==="
Write-Host ""

# --- Python check -----------------------------------------------------------
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $pythonCmd) {
    Write-Host "Error: 'python' (or the 'py' launcher) was not found on PATH."
    Write-Host "Install Python 3.10+ from https://www.python.org/downloads/ and re-run."
    exit 1
}
$systemPython = $pythonCmd.Source
Write-Host "Python: $(& $systemPython --version)"

# --- Virtual environment ----------------------------------------------------
$venvDir    = Join-Path $ScriptDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path $venvDir)) {
    Write-Host "Creating virtual environment (.venv)..."
    & $systemPython -m venv $venvDir
}

if (-not (Test-Path $venvPython)) {
    Write-Host "Error: venv created but $venvPython is missing."
    exit 1
}
Write-Host "Virtualenv: $venvDir"

# --- Dependencies -----------------------------------------------------------
Write-Host "Installing dependencies..."
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -r (Join-Path $ScriptDir "requirements.txt")
Write-Host "Dependencies installed."

# --- Credentials directory --------------------------------------------------
$credDir = Join-Path $ScriptDir "credentials\tokens"
if (-not (Test-Path $credDir)) {
    New-Item -ItemType Directory -Path $credDir -Force | Out-Null
}
Write-Host "Credentials directory ready: $credDir"

# --- config.json ------------------------------------------------------------
$configPath    = Join-Path $ScriptDir "config.json"
$configExample = Join-Path $ScriptDir "config.json.example"
if (-not (Test-Path $configPath)) {
    Copy-Item $configExample $configPath
    Write-Host ""
    Write-Host "Created config.json from template."
    Write-Host ">>> Edit config.json now to add your Gmail account names and addresses. <<<"
    Write-Host ""
}

# --- Print Claude MCP config snippet ----------------------------------------
$serverPath = Join-Path $ScriptDir "server.py"

$mcpConfig = [ordered]@{
    mcpServers = [ordered]@{
        "gmail-hardened" = [ordered]@{
            command = $venvPython
            args    = @($serverPath)
        }
    }
}

Write-Host ""
Write-Host "=== Done! Next steps ==="
Write-Host ""
Write-Host "1. Edit config.json - add your Gmail accounts."
Write-Host ""
Write-Host "2. Get OAuth credentials from Google Cloud Console:"
Write-Host "   - https://console.cloud.google.com/"
Write-Host "   - Create a project -> Enable the Gmail API and Google Calendar API"
Write-Host "   - APIs & Services -> Credentials -> OAuth 2.0 Client ID (Desktop app)"
Write-Host "   - Download JSON and save it as:"
Write-Host "       $ScriptDir\credentials\client_secret.json"
Write-Host "     Or set a separate client_secret path for each account in config.json."
Write-Host ""
Write-Host "3. Authenticate each account:"
Write-Host "       & '$venvPython' setup_auth.py"
Write-Host ""
Write-Host "4. Add the MCP server to Claude Desktop's config file:"
Write-Host "       $env:APPDATA\Claude\claude_desktop_config.json"
Write-Host ""
Write-Host "   Merge this block into that file (keys shown with proper JSON escaping):"
Write-Host ""
$mcpConfig | ConvertTo-Json -Depth 10
Write-Host ""
Write-Host "5. Restart Claude Desktop - the Gmail tools will appear."
