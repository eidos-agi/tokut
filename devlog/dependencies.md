# Dependencies

## 2026-09-27T16:05:00Z pytest (not added to the project)
- **What changed:** Installed pytest in the agent environment only. Did not edit `pyproject.toml` or add a runtime dependency.
- **Why:** The repo has no declared test extra, and `skills/use-tokut/SKILL.md` already says to run `python -m pytest`. pytest is the existing runner (well over 1,000 GitHub stars). No application package was required for the SoR fields.
- **Supporting Research:** https://github.com/pytest-dev/pytest
