---
name: use-tokut
description: >
  Use when the user asks about Tokut, token burn, live token usage, AI cost burn,
  model cost, project token analytics, subscription-covered token usage, API overage
  exposure, how much they are really paying for AI, monthly AI spend, Grok/xAI Build
  cost, OpenAI/Codex, Anthropic/Claude Code, or Google/Gemini CLI monitoring.
---

# Use Tokut — AI cost consultant authority

Tokut is the **canonical local** dashboard and consult API for AI token burn and
cost accounting across OpenAI Codex, Anthropic Claude Code, Google Gemini CLI,
and **Grok Build**. It is also the local store for inference API keys, **tenant-scoped by kai**.
Tenants come from `kai tenants` / GET `/tenants/api` (eidos, aic, arp, gmw,
reeves). Do not invent a sixth tenant. Do not copy secrets across tenants.

## Primary Rule

Use the local Tokut repo or installed `tokut` command as the authority surface.
Do **not** invent parallel cost scripts or freestyle sums over one provider’s
home directory when Tokut can answer. Do **not** equate log meters with card charges
(see `DOMAIN_RULES.md` DR-001..DR-004).

Useful commands:

```bash
cd /path/to/tokut
python run.py --port 8766          # dashboard
python run.py consult              # one-shot JSON: meter / plan credits / metered / cash
python run.py keys list            # masked local API keys
tokut --port 8766
tokut consult
tokut keys list
python -m pytest
```

Open the dashboard:

```text
http://127.0.0.1:8766
http://127.0.0.1:8766/keys
```

Keys are `(tenant, provider)` vault adapters (`inline` or `knox`). Agent
instructions live at the bottom of `/keys` and on `GET /api/keys` as
`agent_instructions`. Hermes `.env` is mirrored only for the laptop tenant
`reeves` on inline puts. Never print secrets; knox slots store a handle only.

Consult API (deterministic briefing — meter vs plan credits vs cash):

```bash
curl -s 'http://127.0.0.1:8766/api/consult' | python -m json.tool
curl -s 'http://127.0.0.1:8766/api/snapshot' | python -m json.tool
```

## Always report ledgers (meter → plan credits → metered → cash)

When answering “how much am I paying / spending / burning?”:

| Ledger | Meaning |
|--------|---------|
| **Meter** | Full list/server value of observed burn (`costUsdTicks` or token × price) |
| **Plan credits (discounted)** | Burn covered by the plan’s included allowance — not cash |
| **Metered** | Burn **above** `included.allowance_usd` — cash-eligible overage |
| **Cash exposure** | Metered slice limited by overage caps / API billing |
| **Recorded cash** | Only if charges were imported — never invent invoices |

Rule of thumb: **up to included allowance = plan credits; above that = metered cash.**

State **confidence**: logs alone → meter + policy; cash charges need billing portal or imports.

## What Tokut Proves

- Local token burn in Codex, Claude Code, Gemini CLI, and Grok Build logs.
- Provider, account, company, project, model, user, day, and hour slices.
- API-equivalent theoretical cost; Grok prefers server cost stamps when present.
- Estimated actual API exposure when accounts are `api_billed`.
- Subscription-covered theoretical burn when accounts are `subscription`.
- Overage **cash ceilings** when `overage.monthly_cap_usd` is configured.
- `/api/consult` headline, top sessions/models, and actions.

## What Tokut Does Not Prove

- Provider invoices or credit-card charges.
- Live SuperGrok weekly pool entitlement percentage from xAI (a human `live_pool` snapshot in `subscriptions.json` is an observation, not a scrape).
- Exact overage dollars spent (cap is a ceiling, not a meter of top-ups). Extra Credits `balance_usd` is likewise an observed snapshot.

For financial decisions, reconcile against provider billing exports or invoices.

## Config (outside the repo)

```text
~/.config/tokut/config.json
~/.config/tokut/subscriptions.json
~/.config/tokut/pricing.json
~/.config/tokut/keys.json
```

Map Grok SuperGrok with overage cap:

```json
{
  "provider": "grok",
  "account": "default",
  "company": "Personal",
  "subscription": "SuperGrok",
  "plan": "SuperGrok",
  "billing_mode": "subscription",
  "included": { "period": "week", "allowance_usd": 200 },
  "overage": { "mode": "auto_topup", "monthly_cap_usd": 50 },
  "notes": "Plan credits up to allowance; metered above; cash ≤ overage cap."
}
```

## Safety Boundary

Cost ingest is read-only. The keys page is the local write path for inference
API keys (`keys.json` mode 600, localhost mutations, GET is last-four only).
Do not add provider writes, billing mutations, account changes, outbound
notifications, or secret-returning APIs without an explicit approval-gated design.
