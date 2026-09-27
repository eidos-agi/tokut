# Knox seam hardening + consult key routes

## 2026-09-27T20:15:00Z A — knox seam
- **What changed:** Kept `resolve()` / `public_resolve()` / CLI `keys resolve|check`
  honest: the default knox path is `use_invoke` plus the `knox request` →
  `approve` → `invoke --env-var … -- <child>` recipe, with no `knox get` and no
  subprocess. `knox_runner` stays a constructor unit-test seam; `server.py` never
  injects one. Added `safe_error_detail()` so a runner error cannot echo a
  key-shaped value or a full `knox:` handle into `detail`, and made the CLI's
  `_safe_keys_json` strip `secret` keys recursively.
- **Why:** A seam that can return a secret must not be reachable from the public
  path or leak through an error string. Session source logs and tests stay free of
  live Knox calls.
- **Supporting Research:** `docs/tenant-ai-keys.md`, `SECURITY.md`, DECISIONS
  D-09/D-10/D-11. No unlock-broker, no live Knox, live `keys.json` untouched.

## 2026-09-27T20:15:00Z B — consult key routes
- **What changed:** Added `KeyStore.consult_routes()` (read-only, reuses
  `list_public`) and wired it through an optional `TokenBurnStore(key_routes=…)`
  provider into `store.consult()`, `GET /api/consult`, dashboard `consult`, and
  `tokut consult`. Each route carries tenant, provider, backend, `is_knox`,
  presence flags for `openrouter_project` / `openrouter_tag` / `spend_alias` /
  `inject`, the safe public project/tag/alias values, inject plane names, and
  Hermes `match`/`drift`. The store tolerates a missing or failing provider.
- **Why:** Burn came from local logs only; the cost consultant could not say
  which tenant/provider routes exist or which are Knox. Presence flags answer
  that without secrets or invented dollars.
- **Supporting Research:** `KeyStore.public_record` / `safe_slot_meta` (already
  the trusted safe projection), D-11 slot model. Fixture KeyStores only; the
  tests never read or write `~/.config/tokut/keys.json`.

## [ ] Follow-ups
- [x] `resolve` / CLI never print a secret; no `knox get`; default recipe unchanged
- [x] `key_routes` additive in consult/API/CLI, no secrets or dollar amounts
- [x] `python3 -m pytest` green (61 passed)
- [ ] Human: wire real knox refs / OpenRouter projects (out of scope here)
