# Keys CLI rebase onto D-11

## 2026-09-27T16:10:00Z Rebase
- **What changed:** Rebased `cursor/keys-cli-resolve-ui-ad3e` onto `origin/main` after PR #6 (D-11). Kept CLI `keys resolve` / `--check` and the `/keys` backend picker, and kept SoR fields (`openrouter_project`, `openrouter_tag`, `spend_alias`, `inject`).
- **Why:** Main moved while PR #5 was open. A merge conflict in `tokut/keys.py` and `README.md` would have dropped either the CLI view or the metadata helpers (`_knox_resolve_base`, `_annotate_slot`).
- **Supporting Research:** `docs/tenant-ai-keys.md`; PR #5; merged PR #6 (`c888758`).

## 2026-09-27T16:10:00Z Decision
- **What changed:** `public_resolve` now copies safe slot metadata onto every record-backed report. Knox reports still come from `_knox_resolve_base` (masked handle, recipe, metadata) and set `error` to `use_invoke` or `missing_ref` without calling `knox_runner`. The keys page list shows those fields and planned inject planes. A page save that omits the fields leaves them stored.
- **Why:** D-11 metadata has to stay visible on the new CLI and UI surfaces. Library `resolve()` can still return an inline secret; the CLI prints `public_resolve` only and drops a `secret` key if one is present.
- **Supporting Research:** D-11 contract in `docs/tenant-ai-keys.md`. No live keys, no Knox process, no `knox get`.

## 2026-09-27T16:10:00Z Refactor note
- **What changed:** Split the CLI view into `public_resolve`, `_public_slot_view`, and `_public_inline_view` so each stays under the 50-line function budget.
- **Why:** The pre-rebase `public_resolve` was already one long method. Folding D-11 annotation into it would have made that worse.
- **Supporting Research:** User rule on function length. `tokut/keys.py` and `tokut/server.py` were already past the 350-line file budget before this rebase (`KeyStore.put` included). New validation stays in `tokut/key_meta.py`. Suggested later refactor: split `put` into inline and ref helpers.

## [ ] Follow-ups
- [x] Conflict resolution keeps D-10 steps 5–6 and D-11 fields
- [x] CHANGELOG notes the rebase
- [x] Tests green (`python3 -m pytest` — 49 passed), including no secret in resolve stdout
- [ ] Keys page checked in the browser with a temp keys file (no live secrets)
