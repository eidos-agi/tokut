# Tokut domain rules — AI cost consultant geometry

World-facts about AI cost. These are true whether or not Tokut is running.
Code and `use-tokut` must obey them. Stake: Daniel confuses meter with cash
(SuperGrok July 2026: ~$563 Build meter vs $50 auto top-up ceiling).

---

```yaml
- id: DR-001
  world_fact: >
    Local tool session logs record compute consumption (tokens and sometimes
    server-stamped dollar ticks). That is a usage meter, not a payment ledger.
  rule: >
    Tokut must always separate meter (API-equivalent / server cost ticks) from
    cash (what may hit a card). Never present a single number as "what you paid"
    when only logs were observed.
  provenance:
    established: 2026-07-24
    by: daniel
    reason: >
      Grok Build updates.jsonl stamped costUsdTicks summing to ~$563 for July
      while SuperGrok auto-rebill cap was $50; user correctly rejected equating
      meter with cash charge.
  blast_radius: store billing summary, consult API, use-tokut skill, dashboard Costs view
  current_encoding: tokut/store.py _billing_summary, _event_cost; skills/use-tokut/SKILL.md
  failure_signature: >
    Agent or UI says "you spent $563" from costUsdTicks alone while subscription
    pool covered most usage.
  enforcement: tests for subscription meter vs paid; skill wording
  last_validated:
    date: 2026-07-24
    by: daniel
    method: local Grok session log investigation
  status: active

- id: DR-002
  world_fact: >
    Subscription products (SuperGrok, Claude Max, ChatGPT Pro/Team, etc.) grant
    an included usage pool. Metered burn inside the pool is not Extra Credits
    cash. Overage (auto top-up, Extra Usage Credits) is a separate cash path
    often capped monthly.
  rule: >
    billing_mode subscription means included meter maps to subscription_theoretical
    with actual charge $0 unless an overage policy is configured. Overage monthly
    caps bound cash exposure, never the meter ceiling.
  provenance:
    established: 2026-07-24
    by: daniel
    reason: SuperGrok Settings Usage is weekly pool; auto top-up has monthly max.
  blast_radius: subscriptions.json schema, _actual_charge_for_events, consult
  current_encoding: tokut/store.py _load_subscriptions overage block; subscriptions.example.json
  failure_signature: >
    Meter $500 shown as paid while auto top-up max is $50 and no invoices imported.
  enforcement: test_subscription_overage_cap_does_not_inflate_meter
  last_validated:
    date: 2026-07-24
    by: daniel
    method: xAI Grok FAQ + local cost investigation
  status: active

- id: DR-003
  world_fact: >
    Some providers stamp authoritative cost on each invocation (e.g. Grok
    costUsdTicks where 1 USD = 10^10 ticks). When present, that stamp beats
    local list-price multiplication for the meter.
  rule: >
    Prefer server cost stamps when complete; fall back to token × pricing table.
    Mark pricing_source so consumers know which path was used.
  provenance:
    established: 2026-07-24
    by: daniel
    reason: Grok headless docs and updates.jsonl turn_completed usage.costUsdTicks
  blast_radius: parser, _event_cost
  current_encoding: tokut/parser.py parse_grok_line; store._event_cost
  failure_signature: Ignoring stamps and under/over pricing Grok relative to server.
  enforcement: test_parse_grok_line_prefers_cost_ticks; test_event_cost_uses_server_stamp
  last_validated:
    date: 2026-07-24
    by: daniel
    method: sample turn_completed events
  status: active

- id: DR-004
  world_fact: >
    Provider invoices and billing portals are the only authority for cash that
    was actually charged. Local logs and config policies cannot prove card charges.
  rule: >
    actual_charge_confidence stays unverified or policy-based unless charges are
    imported. Consult answers must state confidence. Never claim invoice_matched
    from logs alone.
  provenance:
    established: 2026-06-11
    by: daniel
    reason: Original Tokut billing warning; reinforced 2026-07-24
  blast_radius: billing summary, skill, SECURITY
  current_encoding: _billing_summary warning; use-tokut
  failure_signature: "Confirmed charge" language without invoice import.
  enforcement: skill + billing.warning string; confidence fields
  last_validated:
    date: 2026-07-24
    by: daniel
    method: product review
  status: active

- id: DR-005
  world_fact: >
    Tokut is multi-tool. Agent freestyle sums over one provider's home directory
    drift from the fleet picture and re-introduce meter/cash confusion.
  rule: >
    For "how much am I paying / burning for AI", agents must consult Tokut
    (dashboard or /api/consult or use-tokut) as the authority surface, not invent
    parallel cost scripts per provider.
  provenance:
    established: 2026-07-24
    by: daniel
    reason: Ad-hoc Grok cost-analytics skill vs existing Tokut product
  blast_radius: use-tokut skill, marketplace description
  current_encoding: skills/use-tokut/SKILL.md
  failure_signature: New ~/.grok/skills that re-sum logs without Tokut.
  enforcement: skill Primary Rule
  last_validated:
    date: 2026-07-24
    by: daniel
    method: design conversation
  status: active

- id: DR-006
  world_fact: >
    Changing provider billing (top-ups, plans, payment methods) is a high-stakes
    human action. Monitoring tools that write to billing are dangerous.
  rule: >
    Tokut remains read-only. No provider billing mutations, no auto top-up changes,
    no outbound charge notifications without separate approval-gated design.
  provenance:
    established: 2026-06-11
    by: daniel
    reason: SECURITY.md and CONTRIBUTING.md
  blast_radius: entire product
  current_encoding: SECURITY.md
  failure_signature: Code path that calls provider billing APIs to purchase credits.
  enforcement: code review; no write tools in server
  last_validated:
    date: 2026-07-24
    by: daniel
    method: SECURITY.md
  status: active

- id: DR-007
  world_fact: >
    Subscription plans grant discounted included usage (plan credits) valued at
    list/server meter rates. Only burn beyond the included allowance is metered
    cash-eligible (overage / Extra Credits), often with a monthly cash cap.
  rule: >
    Split each account meter into plan_credits_usd (discounted included usage)
    and metered_usd (above included.allowance_usd). Cash exposure applies only
    to metered_usd (capped by overage.monthly_cap_usd when configured). If
    allowance is unset, treat all subscription burn as plan credits and keep
    overage cap as max cash risk only.
  provenance:
    established: 2026-07-24
    by: daniel
    reason: >
      SuperGrok/weekly pools and discounted plan usage; user direction that
      burn above metered/overage is plan credits / discounted included usage.
  blast_radius: _account_cost_allocation, billing, consult, subscriptions.json
  current_encoding: tokut/store.py _account_cost_allocation
  failure_signature: >
    Entire $563 SuperGrok meter shown as cash when most is plan credits and
    only overage above included allowance should be metered.
  enforcement: test_plan_credits_then_metered_overage
  last_validated:
    date: 2026-07-24
    by: daniel
    method: product direction in session
  status: active
```

