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

## D-11: Tenant AI-keys SoR — refs, spend walls, inject recipes
Date: 2026-09-27
Relationship: Builds on D-08 (kai owns the tenant list), D-09 (slots are vault refs), and D-10 (load contract, inline then knox, no unlock-broker). Independent of draft PR #5 (`cursor/keys-cli-resolve-ui-ad3e`).
Chose: Tokut's `~/.config/tokut/keys.json` is the system of record for `(tenant, provider)` refs plus optional `openrouter_project`, `openrouter_tag`, `spend_alias`, and `inject` plane paths. DeepSeek stays direct Knox on `(tenant, deepseek)` (known vault id `knox:bc3fdbe01f704a72`), not OpenRouter BYOK. OpenRouter management keys are the spend wall on `(tenant, openrouter)`. Prim Foundation does not get a duplicate OpenRouter account: `prims` is a planned inject plane with explicit `spend_alias` `eidos` until kai lists it. `ridge` is planned with no spend alias until Daniel names one. Neither id is added to the ADR 0001 fallback. Inject recipes (`dsh_credentials` → `~/.dsh/.credentials.yaml`, `paseo_prims` → `paseo-prims`) live on the slot as placeholders. Tokut orchestrates those recipes for other agents. Fort Knox keeps custody. PrimsDrive/Paseo consume. SafePaste is a temporary bootstrap only when Knox is blocked and Daniel re-stamps; Tokut performs it; it is not the SoT. Public list/API/CLI never return secrets.
Over: A sixth plaintext store for prims/ridge; OpenRouter BYOK for DeepSeek on dsh; chat or SafePaste as the key store; Tokut unwrapping Knox; flipping Paseo off the interim yaml; implementing unlock-broker in this change.
Because: Daniel wants per-tenant OpenRouter spend walls and Tokut-owned DeepSeek on paseo-prims, while D-08 still says kai defines tenants and "no sixth store." The existing KeyStore slot plus optional fields holds that without a new secret file. D-09's line that Tokut does not own Paseo inject policy is narrowed: Tokut owns the recipe and the orchestration; it still does not custody the secret or flip the interim file. D-10 steps through migrate/unwrap stay as they were; this records the SoR those steps write into.
D-08 tension, stated plainly: kai has not been shown to list `prims` or `ridge`. Inventing them in the ADR fallback would create stores when the door is down. Leaving them undocumented would make agents open a secret slot anyway. Planned planes plus `spend_alias` is the honest middle. If kai already lists them in an environment, they are normal tenants and the planned row drops.
Risk: Someone treats `planned_inject_planes` as a tenant allow-list, or writes a secret into `inject` / project metadata. Put rejects secret-shaped metadata; list redacts it. Live keys are not migrated here, so inline slots remain until a human wires the Knox ref.
v2 might reverse this if: Daniel creates a real Prim Foundation OpenRouter project (drop the eidos alias), or kai permanently omits prims/ridge (delete the planned rows), or one vault product replaces per-tenant spend walls.

## D-10: Keys adapter rollout — load contract first, then backends
Spend walls and plane recipes: D-11. This rollout still does not unwrap Knox, flip Paseo, or build unlock-broker.
Date: 2026-09-05
Chose: Today's `KeyStore._load` drops any record without a `secret` field, so ref-only slots would vanish until load/save accept `secret` OR `ref` (+ backend/inject); bump file version to 3 if needed. Call surface is small and in-repo only: KeyStore `put` / `get_secret` / `delete`, localhost POST/GET/DELETE `/api/keys`, CLI `keys put|list|delete|import-hermes`, Hermes `.env` mirror for `reeves` only. No Knox/Paseo callers in this repo. Rollout: (1) load/save accept ref|secret, (2) wrap today's plaintext as `inline` backend (tests stay green), (3) `knox` backend stub (store handle only; resolve via knox or report needs-unlock — never write secret), (4) API dual POST `{backend,ref}` or legacy `{secret}`, (5) CLI `resolve`/`--check` without printing secrets, (6) UI backend+handle (secret box = legacy/migrate), (7) migrate live DeepSeek slots to knox handle, (8) retire writing secrets once no inline slots remain, (9) unlock-broker / Paseo provider flip stay out of Tokut scope (Fort Knox / Paseo). First implementation PR: steps 1+2+3 with existing plaintext tests still green.
Over: Jumping to UI/migrate before fixing load; treating Knox/Paseo inject as Tokut's job; one big-bang rewrite of keys.json
Because: Confidence pass on live `tokut/keys.py` 2026-09-05; Daniel asked to increase confidence then record this in DECISIONS.md. Builds on D-09.
Risk: Live keys.json inventory unknown until local inventory — migrate/retire timing stays ~60% confident; Hermes mirror may still hold plaintext after Tokut refs until step 8
v2 might reverse this if: A single mandated vault makes intermediate `inline` unnecessary, or Paseo starts calling Tokut resolve directly (then inject policy might move into Tokut)

## D-09: Keys are vault adapters (refs), not a secret store
Rollout detail: D-10. Paseo inject recipes (not custody, not the interim-yaml flip): D-11.
Date: 2026-09-05
Chose: Store vault refs/handles + inject recipes per slot `(tenant, provider)`, not secrets as source of truth. Backends are pluggable: knox, env, file, keeper, and migrate-only `inline` (today's keys.json plaintext). Knox is one backend among many. Inject paths (env child-process, short-lived file-write then shred, optional Hermes mirror for reeves, `tokut keys resolve/--check`) are recipes on the slot; Tokut does not own Paseo plane inject policy (Paseo/wrapper does). Keep reading plaintext keys.json as `inline`; add ref+inject fields; move DeepSeek to knox:bc3fdbe01f704a72 when wiring; drop secrets from disk once every live slot has a non-inline ref.
Over: Tokut as the local inference-key store (D-07); Knox special-cased forever; secrets in keys.json as source of truth
Because: Daniel: "tokut should have a keys adapter to any key system not just knox"; first-principles pause 2026-09-05. Supersedes D-07.
Risk: Dropping `inline` before every live slot has a non-inline ref breaks callers; adapter bugs leave plaintext on disk
v2 might reverse this if: A single vault is mandated and Tokut only indexes presence, or air-gap requires secrets back on disk

## D-08: Kai tenants are Tokut tenants
prims and ridge: D-11. Not ADR tenants. Not a sixth secret store.
Date: 2026-09-05
Chose: Key slots are `(tenant, provider)`. Tenant list is live `kai tenants` / `/tenants/api`. ADR 0001 five stores (eidos, aic, arp, gmw, reeves) only if the door is down. Hermes `.env` mirror is reeves only.
Over: A single global key ring; inventing a sixth Tokut tenant; copying secrets across tenants
Because: Daniel: "the tenants in kai will define the tenants in tokut"
Risk: kai OAuth down → ADR fallback. Labeled as such. Still no sixth store.
v2 might reverse this if: kai door is always reachable and cache is enough

## D-07: Tokut is the local inference-key store
Superseded by D-09 (2026-09-05).
Date: 2026-09-05
Chose: Store API keys in `~/.config/tokut/keys.json` (0600), serve a localhost `/keys` page, return last-four only on GET, and mirror env vars into `~/.hermes/.env`
Over: Leave keys only in Hermes `.env` / Knox; make Tokut stay strictly read-only
Because: Daniel asked Tokut to hold OpenRouter and DeepSeek keys and wanted a simple page to add them. Cost burn and credential presence belong on the same local dashboard.
Risk: A cost tool now writes secrets. Mitigate with localhost-only mutations, no secret in GET/logs, 0600 file, no CLI `--secret` argv.
v2 might reverse this if: Knox becomes the only agent-facing vault and Tokut only indexes key *presence*

## D-06: Plan credits vs metered overage (discounted AI usage)
Date: 2026-07-24
Chose: `included.allowance_usd` + split meter into `plan_credits_usd` / `metered_usd` / cash
Over: Binary subscription=$0 for entire meter only
Because: Plans are discounted included usage; only burn above the included allowance is cash-metered
Risk: Allowance must be configured (weekly pool $ unknown without portal); wrong allowance mis-splits
v2 might reverse this if: Provider exports live remaining pool %

