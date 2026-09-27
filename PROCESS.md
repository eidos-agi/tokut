# Process

## 2026-07-24 — Meter vs cash, Grok, consultant codification

Started from Daniel wanting `/cost` for Grok and monthly analytics. Built-in
`/cost` is session-only. Local `costUsdTicks` summed to ~$563 for July Build on
one laptop. Daniel rejected that as "what I paid" — auto top-up max was $50.

Considered keeping a Grok-only skill under `~/.grok/skills/cost-analytics`.
Rejected as long-term home: Tokut already owns dual ledger (paid vs
subscription-covered), company mapping, and `use-tokut` as agent authority.
Codifying the lesson only outside Tokut would force every agent to relearn
meter ≠ cash.

Reframed Tokut as the AI cost consultant surface: complete ingest (Grok),
prefer server stamps, model overage caps on subscription rows, expose
deterministic `consult`, freeze domain rules so the next agent does not re-walk
the $563 path.

Deliberately not in this pass: invoice import, scraping grok.com, SQLite
multi-month store, multi-host merge, LLM-in-dashboard.

## 2026-09-05 — Local keys page

Hermes was still on NVIDIA Nemotron. Daniel had OpenRouter and DeepSeek keys
and asked Tokut to store them, with a simple page to add keys if no frontend
existed. The burn dashboard already existed; it had no credential surface.

Added `~/.config/tokut/keys.json` (0600), `/keys`, localhost-only PUT/DELETE,
masked GET, CLI `tokut keys`, and a Hermes `.env` mirror so the agent can
actually use the key after save. Did not take secrets on the command line.

## 2026-09-27 — Tenant AI-keys system of record

Daniel wants Tokut to own refs and inject recipes for other agents, starting
with DeepSeek on paseo-prims, plus per-tenant OpenRouter spend walls. D-08 still
forbids a sixth secret store, and kai has not been shown to list `prims` or
`ridge`. Recorded D-11: optional slot metadata on the existing KeyStore, planned
planes instead of ADR entries, Prim Foundation `spend_alias` → `eidos`, SafePaste
only as a re-stamped fallback. Did not migrate live keys, call Knox, flip the
interim dsh yaml, or build unlock-broker.
