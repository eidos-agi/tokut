# Duplicates

## 2026-09-27T15:50:00Z Kept
- **What changed:** `tests/test_key_meta.py` has its own `_store` helper instead of importing `tests/test_keys.py`.
- **Why:** The existing helper is private to a module that is not a package. Importing it would couple two test modules and rewrite a stable import path. The new helper adds a tenant-list argument the old tests do not need.
- **Supporting Research:** None.
