# Gmail and Calendar MCP - Cross-Platform Hardened Fork

A local Model Context Protocol (MCP) server for multiple Gmail accounts and
Google Calendars. This derivative of
[DiegoMaldonadoRosas/gmail-mcp](https://github.com/DiegoMaldonadoRosas/gmail-mcp)
supports macOS, Linux, and Windows while adding guardrails for mailbox actions
and content returned to an AI client.

For a browser-friendly public setup and security summary, see
[`docs/gmail-mcp-hardened-report.html`](docs/gmail-mcp-hardened-report.html).

## Features

- Multi-account Gmail search, reading, drafts, labels, and trash handling.
- Read-only Google Calendar listing and event search.
- macOS/Linux setup through `setup.sh` and Windows setup through `setup.ps1`.
- Per-account OAuth client-secret paths, with a shared-secret fallback.
- Preview plus a one-time confirmation token for sending email, changing
  labels, and moving mail to Trash.
- Attachment sends and downloads restricted to the user's `Downloads`,
  `Documents`, or `Desktop` directories.
- Untrusted-content envelopes for email and calendar content, sanitised
  unexpected errors, and stderr audit entries for mutations.

## Requirements

- Python 3.10 or later.
- Claude Desktop or another stdio MCP client.
- A Google Cloud OAuth Desktop client with the Gmail API and Google Calendar
  API enabled.

## Install

Clone your published fork, then run the setup command for your platform.

macOS or Linux:

```bash
bash setup.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

The script creates `.venv`, installs dependencies, creates local credential
directories, creates `config.json` from the template if needed, and prints an
MCP configuration snippet containing absolute paths.

## Configure Accounts

Edit the generated `config.json`. A separate Google Cloud OAuth client for
each mailbox is recommended:

```json
{
  "accounts": {
    "personal": {
      "email": "you@gmail.com",
      "description": "Personal Gmail",
      "client_secret": "./credentials/personal_client_secret.json"
    },
    "work": {
      "email": "you@company.com",
      "description": "Work Gmail",
      "client_secret": "./credentials/work_client_secret.json"
    }
  },
  "credentials_dir": "./credentials"
}
```

For a single shared OAuth client, omit `client_secret` from each account and
place the downloaded file at `credentials/client_secret.json`.

Then authenticate:

```bash
.venv/bin/python setup_auth.py
```

On Windows:

```powershell
.\.venv\Scripts\python.exe setup_auth.py
```

A browser opens once for each account. Re-run authentication after changing
OAuth scopes or adding accounts.

## MCP Client Configuration

Use the JSON printed by the setup script. Typical macOS/Linux configuration:

```json
{
  "mcpServers": {
    "gmail-hardened": {
      "command": "/absolute/path/to/gmail-mcp/.venv/bin/python",
      "args": ["/absolute/path/to/gmail-mcp/server.py"]
    }
  }
}
```

Typical Windows configuration:

```json
{
  "mcpServers": {
    "gmail-hardened": {
      "command": "C:\\absolute\\path\\to\\gmail-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\absolute\\path\\to\\gmail-mcp\\server.py"]
    }
  }
}
```

Claude Desktop config locations:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

## Safety Model

Email bodies, subject lines, sender fields, draft content, calendar names, and
calendar events are external input. Tools that return them include a warning
telling the MCP client to treat those values as data rather than instructions.

All write tools first return a preview: `gmail_send`, `gmail_create_draft`,
`gmail_modify_labels`, `gmail_trash`, and `gmail_download_attachment`. They do
nothing until called again with identical inputs, `confirm: true`, and the
one-time `confirmation_token` returned by that preview. A confirmed draft
creates visible Gmail content but does not send mail.

Attachments can only be read from or saved within `~/Downloads`,
`~/Documents`, or `~/Desktop`; paths are resolved before checking to prevent
symlink escapes. The server also refuses to attach its own credential
directory or common key/secret file types. Downloaded attachment bytes remain
untrusted.

Tokens and client secrets stay local under `credentials/`, which is excluded
from Git. Token writes request user-only file permissions where the operating
system supports them. On Windows, store the project inside your user profile
and check directory ACLs if the computer is shared.

The OAuth scope set is limited to `gmail.modify`,
`calendar.calendarlist.readonly`, and `calendar.events.readonly`. This MCP
does not provide cloud-file upload or file-sharing operations; those belong
in a separate service with separate consent and audit controls.

See [`SECURITY.md`](SECURITY.md) for the threat model and residual risks.

## Available Tools

| Area | Tools |
| --- | --- |
| Account | `list_accounts` |
| Gmail read | `gmail_get_profile`, `gmail_search`, `gmail_read_message`, `gmail_read_thread`, `gmail_list_drafts`, `gmail_list_labels` |
| Gmail write | `gmail_send`, `gmail_create_draft`, `gmail_modify_labels`, `gmail_trash` |
| Attachments | `gmail_download_attachment` |
| Calendar read | `calendar_list_calendars`, `calendar_list_events`, `calendar_search`, `calendar_get_event` |

## Publishing

The `Mac/` and `Windows/` directories in the assembly workspace are ignored
because they contain comparison inputs and may include secrets or generated
files. Publish only the tracked root project files. See
[`docs/COMPARISON.md`](docs/COMPARISON.md) for merge decisions and
[`NOTICE.md`](NOTICE.md) for upstream attribution.

## Test

After dependencies are installed, run:

```bash
python -m unittest discover -s tests
```

The smoke test imports the server with template-only configuration and checks
that the intended cross-platform tool surface is registered; it does not make
Google API calls.
