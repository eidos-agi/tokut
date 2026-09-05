# Changelog

## Unreleased

- **Keys adapters (D-09 / D-10 steps 1–3):** `KeyStore` load/save accepts `secret` **or** `ref` so vault handles are not dropped. File version 3 when refs are present; v2 plaintext still loads as `inline`.
- **`inline` backend:** today's plaintext slots. `resolve()` returns the stored secret. `put` + Hermes mirror for `reeves` unchanged.
- **`knox` stub:** `put` / `set_ref` store `{backend: knox, ref}` with no secret. Public list shows backend + masked handle. `resolve()` may call `knox get` or return `needs_unlock` / `not_implemented_for_daemon` — never writes the secret back to `keys.json`.
- **API:** GET includes `backend` and safe ref metadata. POST accepts legacy `{secret}` or `{backend, ref}`.

## 0.3.1 - 2026-09-05

- **Kai tenants own Tokut tenants.** Keys are `(tenant, provider)`. Tenant list is `kai tenants` / GET `/tenants/api`; ADR 0001 five-store list is fallback only if the door is down. No sixth tenant.
- **Provenance:** source, source_path, created/rotated, sha256 fingerprint, vendor prefix, Hermes match/drift, history. GET still never returns the secret.
- **Agent instructions** at the bottom of `/keys` and on `GET /api/keys` as `agent_instructions`.
- Hermes `.env` mirror is only for the laptop tenant (`reeves`).

## 0.3.0 - 2026-09-05

- **Local inference keys:** Tokut stores API keys in `~/.config/tokut/keys.json` (mode 600). GET `/api/keys` returns last-four only.
- **Keys page:** `http://127.0.0.1:8766/keys` — add/replace/remove OpenRouter, DeepSeek, and other inference keys. Writes stay on localhost.
- Saving a key also upserts the matching env var in `~/.hermes/.env` so Hermes can use it. `tokut keys import-hermes` copies the other direction.
- CLI: `tokut keys list|put|delete|import-hermes`. Put reads `--from-env` or `--secret-file`, never a secret argv.

## 0.2.1 - 2026-08-25

- Subscription rows may carry a human `live_pool` snapshot, Extra Credits balance, auto top-up trigger/amount, and `not_this_pool` notes. Consult surfaces them as observed facts, not a live xAI scrape.

## 0.2.0 - 2026-07-24

- **AI cost consultant residue:** `DOMAIN_RULES.md`, `DECISIONS.md`, `PROCESS.md` — meter vs cash, overage caps, Grok stamps.
- **Grok Build provider:** watches `~/.grok/sessions/**/updates.jsonl` `turn_completed` usage.
- **Server cost stamps:** prefers `costUsdTicks` (1 USD = 10^10 ticks) over list-price when present.
- **Overage policy** on subscription rows: `overage.mode` + `overage.monthly_cap_usd` → `billing.overage_cap_usd` / `cash_exposure_max_usd`.
- **Plan credits / discounted usage (DR-007):** `included.allowance_usd` splits meter into `plan_credits_usd` vs `metered_usd`; cash only on the metered slice.
- **`/api/consult`** and dashboard `consult` object: headline, ledgers, top sessions/models, actions.
- Updated `use-tokut` skill as multi-tool cost consultant authority (includes Grok).

## 0.1.0 - 2026-06-11

- Initial Tokut source repo.
- Added read-only local dashboard for OpenAI Codex, Anthropic Claude Code, and Google Gemini CLI token burn.
- Added company/subscription mapping, API-equivalent cost estimates, project/model/minute/hour views, right-side filter rail, and Eidos marketplace plugin metadata.
