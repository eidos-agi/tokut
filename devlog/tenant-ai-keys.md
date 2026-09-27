# Tenant AI keys

## 2026-09-27T15:50:00Z Decision
- **What changed:** D-11 records Tokut as the system of record for tenant AI-key refs and inject recipes. Optional slot fields are `openrouter_project`, `openrouter_tag`, `spend_alias`, and `inject`. `prims` and `ridge` stay planned planes, not ADR tenants.
- **Why:** The existing `(tenant, provider)` KeyStore already stores Knox refs and an inject recipe. A new secret file would violate D-08. DeepSeek stays direct Knox. OpenRouter project metadata is the spend wall. Prim Foundation spend is `spend_alias` → `eidos` until kai lists `prims` and Daniel creates a separate project (default: do not).
- **Supporting Research:** `DECISIONS.md` D-08, D-09, D-10; `tokut/keys.py`; `tokut/tenants.py`; live inventory note in the task (2026-09-05). Draft PR #5 was not used as a base.

## 2026-09-27T15:50:00Z Implementation
- **What changed:** `tokut/key_meta.py` validates and redacts metadata. `KeyStore.put` / `set_ref`, POST `/api/keys`, and `tokut keys put` accept the fields. `GET /api/keys` includes `planned_inject_planes`. Docs: `docs/tenant-ai-keys.md`.
- **Why:** The model has to round-trip in the store, not only in markdown. Public surfaces must not print secrets.
- **Supporting Research:** None beyond the repo. No Knox calls, no live migration, no unlock-broker, no Paseo yaml flip.

## 2026-09-27T15:50:00Z Refactor note
- **What changed:** Nothing extracted from `KeyStore.put`.
- **Why:** `put` was already over the 50-line function budget (secret path and ref path share one method). New metadata is delegated to `slot_metadata` instead of growing both branches inline. Suggested later refactor: split inline put and ref put into two helpers that both call `slot_metadata`.
- **Supporting Research:** User rule on function length. Splitting `put` in this change would rewrite a path that already has passing tests. `tokut/keys.py` and `tokut/server.py` were already past the 350-line file budget before this change. New validation lives in `tokut/key_meta.py` (under that budget) instead of pushing more branches into `put`.

## [ ] Follow-ups
- [x] Document DeepSeek vs OpenRouter, slot metadata, SoR, inject recipes, SafePaste SOP, Prim Foundation alias, ownership
- [x] D-11 and pointers from D-08 / D-09 / D-10
- [x] Schema, redaction, tests
- [ ] Human proof after merge: inject DeepSeek onto paseo-prims via Knox, or SafePaste only with a fresh stamp
