# Tests

## 2026-09-27T16:05:00Z pytest
- **What changed:** Ran the suite after the D-11 schema and docs landed.
- **Why:** Confirm metadata round-trip, secret redaction, planned planes, API, and the existing keys tests.
- **Supporting Research:** `python3 -m pytest tests/test_keys.py tests/test_key_meta.py tests/test_keys_api.py tests/test_store.py tests/test_parser.py tests/test_provider_parsers.py` — 41 passed.

## 2026-09-27T16:15:00Z pytest
- **What changed:** Re-ran the full suite after rebasing D-10 steps 5–6 onto D-11.
- **Why:** Confirm CLI resolve/--check, keys page markup, and SoR metadata still pass together, with no secret in public resolve output.
- **Supporting Research:** `python3 -m pytest` — 49 passed. Browser check used a temp keys file on `127.0.0.1:8766/keys` (backend toggle, knox save, masked row, metadata line).

## 2026-09-27T20:15:00Z pytest
- **What changed:** Added the knox-seam hardening tests and the read-only `consult` / `key_routes` tests.
- **Why:** Prove the public path never calls `knox_runner`, runner errors are redacted, and consult/API/CLI routes carry no secret, full handle, or invented dollar amount.
- **Supporting Research:** `python3 -m pytest` — 61 passed. All key fixtures are `tmp_path`; the live `~/.config/tokut/keys.json` is never read or written.
