# Security

Tokut watches local logs and serves a local dashboard. Cost ingest stays read-only.
The keys page is the one local write path: inference API keys on this Mac.

## Supported Boundary

- Reads local Codex, Claude Code, Gemini CLI, and Grok Build session logs.
- Reads optional local pricing/subscription config (including overage caps).
- Serves on localhost by default.
- Does not send data to external services.
- Does not mutate provider accounts, billing, or subscriptions.
- May write inference API keys or vault refs to `~/.config/tokut/keys.json`
  (mode 600). Inline (plaintext) puts for `reeves` still mirror env vars into
  `~/.hermes/.env`. Knox slots store a handle only — resolve must not write the
  secret back into `keys.json`. GET `/api/keys` never returns the secret, only
  last-four / a masked handle plus `backend`. Key mutations are rejected unless
  the client is loopback.

## Reporting

Report security issues privately to Eidos AGI before public disclosure.

## High-Risk Changes

Any future feature that sends data off-machine, changes provider settings,
writes notifications, exports billing data, returns full secrets over HTTP,
or listens on non-localhost interfaces requires explicit review and
approval-gated design.
