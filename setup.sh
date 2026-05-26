#!/usr/bin/env bash
# Gmail Multi-Account MCP — first-time setup
# Run once: bash setup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Gmail Multi-Account MCP Setup ==="
echo ""

# ── Python check ────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is required but not found."
  exit 1
fi
echo "Python: $(python3 --version)"

# ── Virtual environment ──────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment (.venv)..."
  python3 -m venv .venv
fi
source .venv/bin/activate
echo "Virtualenv: $VIRTUAL_ENV"

# ── Dependencies ────────────────────────────────────────────────────────────
echo "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "Dependencies installed."

# ── Credentials directory ───────────────────────────────────────────────────
mkdir -p credentials/tokens
chmod 700 credentials credentials/tokens
echo "Credentials directory ready: credentials/"

# ── config.json ─────────────────────────────────────────────────────────────
if [ ! -f "config.json" ]; then
  cp config.json.example config.json
  chmod 600 config.json
  echo ""
  echo "Created config.json from template."
  echo ">>> Edit config.json now to add your Gmail account names and addresses. <<<"
  echo ""
fi

# ── Print Claude MCP config snippet ─────────────────────────────────────────
PYTHON_PATH="$SCRIPT_DIR/.venv/bin/python"
SERVER_PATH="$SCRIPT_DIR/server.py"

echo ""
echo "=== Done! Next steps ==="
echo ""
echo "1. Edit config.json — add your Gmail accounts (already open if you just ran this)."
echo ""
echo "2. Get your OAuth credentials from Google Cloud Console:"
echo "   • https://console.cloud.google.com/"
echo "   • Create a project → Enable Gmail API and Google Calendar API"
echo "   • APIs & Services → Credentials → OAuth 2.0 Client ID (Desktop app)"
echo "   • Download JSON → save as:  $SCRIPT_DIR/credentials/client_secret.json"
echo "     Or set a separate client_secret path for each account in config.json."
echo ""
echo "3. Authenticate each account:"
echo "   source .venv/bin/activate && python setup_auth.py"
echo ""
echo "4. Add the MCP server to Claude Code (~/.claude/settings.json):"
echo "   or Claude Desktop (~/Library/Application Support/Claude/claude_desktop_config.json)"
echo ""
echo '   "mcpServers": {'
echo '     "gmail-hardened": {'
echo "       \"command\": \"$PYTHON_PATH\","
echo "       \"args\": [\"$SERVER_PATH\"]"
echo '     }'
echo '   }'
echo ""
echo "5. Restart Claude — the Gmail tools will appear automatically."
