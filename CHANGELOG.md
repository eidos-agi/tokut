# Changelog

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
