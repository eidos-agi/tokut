# Tests

## 2026-09-27T16:05:00Z pytest
- **What changed:** Ran the suite after the D-11 schema and docs landed.
- **Why:** Confirm metadata round-trip, secret redaction, planned planes, API, and the existing keys tests.
- **Supporting Research:** `python3 -m pytest tests/test_keys.py tests/test_key_meta.py tests/test_keys_api.py tests/test_store.py tests/test_parser.py tests/test_provider_parsers.py` — 41 passed.
