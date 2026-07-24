# Decisions

## D-01: Three ledgers, not one number
Date: 2026-07-24
Chose: Always report meter (API-equiv / server ticks), cash exposure (policy), and optional recorded cash (import later)
Over: Single "cost" field; treating costUsdTicks as invoice
Because: SuperGrok meter ≠ card charge; $50 auto top-up is a cash ceiling
Risk: Users still glance at the biggest number
v2 might reverse this if: Providers expose unified cash APIs Tokut can read read-only

## D-02: Grok is a first-class provider via updates.jsonl
Date: 2026-07-24
Chose: Parse `~/.grok/sessions/**/updates.jsonl` turn_completed usage
Over: Separate grok-only skill outside Tokut
Because: Tokut is the multi-tool authority; Grok was the blind spot
Risk: Log format drift; large files; weird timestamps
v2 might reverse this if: Grok ships a stable usage export file

## D-03: Prefer server cost stamps over list price when present
Date: 2026-07-24
Chose: `costUsdTicks / 1e10` as meter when stamped
Over: Always token × local pricing table
Because: Headless docs say ticks reconcile to usage export; more accurate for Grok Build
Risk: OAuth stamps may be incomplete; partial stamps already omitted by Grok
v2 might reverse this if: Stamps proven wrong vs invoices

## D-04: Overage caps live on subscription rows, not a second billing system
Date: 2026-07-24
Chose: Optional `overage: { mode, monthly_cap_usd }` on accounts in subscriptions.json
Over: New billing_mode values only; hardcoding SuperGrok
Because: Same pattern works for any sub with Extra Credits / auto top-up
Risk: Cap is ceiling not spent amount without pool telemetry
v2 might reverse this if: We import weekly pool % from providers

## D-05: Consult is deterministic JSON, not an LLM inside Tokut
Date: 2026-07-24
Chose: `/api/consult` + `store.consult()` pure functions over events + policy
Over: Embedding a chat model in the dashboard
Because: Read-only, testable, agent-consumable; skill/LLM is the face outside
Risk: Advice quality limited to rules
v2 might reverse this if: Local model is wired through eidos-inference with budgets

## D-06: Plan credits vs metered overage (discounted AI usage)
Date: 2026-07-24
Chose: `included.allowance_usd` + split meter into `plan_credits_usd` / `metered_usd` / cash
Over: Binary subscription=$0 for entire meter only
Because: Plans are discounted included usage; only burn above the included allowance is cash-metered
Risk: Allowance must be configured (weekly pool $ unknown without portal); wrong allowance mis-splits
v2 might reverse this if: Provider exports live remaining pool %

