# Source Comparison and Merge Decisions

Prepared on 26 May 2026 from two local variants derived from upstream commit
`9ae20b6` of `DiegoMaldonadoRosas/gmail-mcp`.

## Inputs

| Input | Observed purpose | Material not suitable for publication |
| --- | --- | --- |
| `Mac/gmail-mcp-hardened-share.zip` | Hardened portable Python version and a macOS-oriented usage skill | User-specific skill text and report metadata |
| `Windows/` | Windows setup, attachment handling, and out-of-scope file-sharing/rich-composition experiments | `credentials/`, OAuth tokens, `config.json`, `.venv/`, reports, nested Git data |

## Included in This Version

| Capability | Source or decision |
| --- | --- |
| Gmail and read-only Calendar services | Upstream plus hardened Mac variant |
| `setup.sh` for macOS/Linux | Portable shell installer from the Mac variant |
| `setup.ps1` for Windows | Windows installer, updated for Calendar and per-account secrets |
| Per-account OAuth secrets and Calendar scope | Hardened Mac variant |
| Account-name validation and safer token diagnostics | Hardened Mac variant |
| Send/label/trash confirmation previews | Hardened Mac variant |
| Untrusted-content response envelope and safer errors | Hardened Mac variant |
| Attachment upload/download allowlist and audit records | Hardened Mac variant |
| Restrictive token permission attempt | Added during cross-platform merge |
| Calendar-list untrusted envelope and first-download-directory fix | Added during cross-platform merge |
| Credential-directory attachment block and one-time mutation confirmations | Added during final security review |
| Least-privilege Gmail/Calendar OAuth scope set | Added during final security review |
| Direct dependency pins and CI vulnerability audit | Added during final security review |

## Excluded From This MCP

The local Windows input also included rich-composition and cloud-file
upload/link-sharing experiments. They are not part of this public MCP. File
sharing is a separate disclosure capability and should be implemented, scoped,
tested, and audited in a separate MCP.

## Publish Check

Before creating a public GitHub repository:

1. Confirm `git status --ignored` shows `Mac/`, `Windows/`, `credentials/`,
   `config.json`, `.venv/`, HTML reports, and zip archives as ignored.
2. Run a secret scan over tracked files.
3. Review the attribution in `NOTICE.md` and the MIT statement inherited from
   upstream.
4. Test OAuth and MCP registration independently on macOS and Windows.
