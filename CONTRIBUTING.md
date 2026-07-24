# Contributing

Tokut is an Eidos AGI tool for read-only local token-burn monitoring.

## Development

```bash
python -m pytest
python run.py --port 8766
```

Keep changes scoped and preserve the read-only boundary. Tokut may read local
session logs and local subscription mapping files, but it must not mutate
provider state, send notifications, or change billing/account settings.

## Review

Before publishing:

- Run `python -m pytest`.
- Run `python -m py_compile run.py tokut/*.py`.
- Run `felix plugin doctor` against the marketplace bundle when Felix is available.
- Confirm marketplace manifests parse and the Tokut bundle resolves.
