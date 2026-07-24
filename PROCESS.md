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
