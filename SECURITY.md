# Security

Tokut is read-only by default. It watches local logs and serves a local dashboard.

## Supported Boundary

- Reads local Codex, Claude Code, Gemini CLI, and Grok Build session logs.
- Reads optional local pricing/subscription config (including overage caps).
- Serves on localhost by default.
- Does not send data to external services.
- Does not mutate provider accounts, billing, subscriptions, or local AI tool state.

## Reporting

Report security issues privately to Eidos AGI before public disclosure.

## High-Risk Changes

Any future feature that sends data off-machine, changes provider settings,
writes notifications, exports billing data, or listens on non-localhost
interfaces requires explicit review and approval-gated design.
