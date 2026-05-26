# Security Model

## Scope

This MCP exposes Gmail read, draft, send, label, trash, and attachment
download actions, together with read-only Calendar list/event actions. It does
not expose file-sharing or cloud-file upload operations.

OAuth requests are limited to:

- `https://www.googleapis.com/auth/gmail.modify`
- `https://www.googleapis.com/auth/calendar.calendarlist.readonly`
- `https://www.googleapis.com/auth/calendar.events.readonly`

Google documents `gmail.modify` as allowing Gmail read, compose, and send
operations without immediate permanent deletion. The two Calendar scopes
correspond to the list and event read methods used by this server.

## Guardrails

- Email, draft, label, and calendar data returned to the client is marked as
  untrusted content.
- Every write tool returns a preview and requires a one-time, ten-minute
  `confirmation_token` with identical arguments before execution.
- Executed writes emit audit records to stderr.
- Outbound local attachments are allowed only from `Downloads`, `Documents`,
  or `Desktop`, after resolving symlinks.
- The configured credential directory, configured OAuth client-secret files,
  and common private-key/secret filenames are refused as outbound attachments.
- Downloaded attachments are saved only inside the same allowed user
  directories and are never automatically opened or executed.
- Local configuration, OAuth secrets, tokens, reports, and comparison inputs
  are excluded from version control.
- Runtime direct dependencies are pinned and audited for known
  vulnerabilities in CI.

## Residual Risks

- The server can enforce a preview round trip, but it cannot determine whether
  a user actually read or approved that preview. The MCP client must obtain
  meaningful user confirmation.
- A stolen OAuth token is not constrained by this server's confirmation
  controls. Protect the local `credentials/` directory and revoke compromised
  grants promptly.
- The Gmail scope is inherently powerful because this MCP reads and changes
  mail and sends messages. Users should connect only accounts for which that
  access is acceptable.
- Content warnings reduce prompt-injection risk but do not make message or
  calendar content trustworthy.
- Transitive dependencies are not distributed with hashes; public maintainers
  should review dependency updates and consider generating platform-specific
  hash-locked installation artifacts for higher-assurance deployments.
- A local attacker with access to the same account and filesystem may be able
  to race file checks or replace files after preview. This server is not a
  sandbox against a compromised workstation.

## Reporting

Do not include OAuth tokens, client-secret JSON files, mailbox content, or
personal configuration in public issue reports. Revoke affected credentials
before sharing diagnostic material if exposure is suspected.
