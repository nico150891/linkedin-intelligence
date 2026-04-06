# Contributing

Thanks for your interest in linkedin-intelligence.

This is a personal portfolio project maintained by [@nico150891](https://github.com/nico150891).
**The `main` branch is protected** — all changes go through pull requests and require
explicit approval before merging. Please read this guide before opening a PR.

---

## What contributions are welcome

- Bug fixes
- New LLM provider adapters (see guide below)
- Improvements to the synthetic sample data in `data/sample/`
- Documentation fixes

## What to discuss first (open an issue before coding)

- New features or significant behavior changes
- Changes to the data pipeline architecture
- New dependencies

---

## Development setup

```bash
git clone https://github.com/nico150891/linkedin-intelligence.git
cd linkedin-intelligence
pip install -e ".[dev]"
playwright install chromium
cp .env.example .env
pre-commit install
```

Verify your setup:
```bash
make lint      # ruff + mypy --strict must pass clean
make test      # all unit tests must pass
make sample-run  # full pipeline with synthetic data
```

---

## Branch workflow

```
main          ← protected, requires PR + approval to merge
  └── your-feature-branch  ← work here, then open PR to main
```

- Branch from `main`
- One feature or fix per branch
- Name your branch descriptively: `fix/ollama-health-check`, `feat/add-openai-provider`

---

## Code standards

All of these must pass before a PR will be reviewed:

```bash
make lint   # ruff check + ruff format --check + mypy --strict
make test   # pytest tests/unit/ — no failures, no new untested code
```

Key rules (full details in `CLAUDE.md`):
- Type hints on every function — `mypy --strict` must pass
- No `dict[str, Any]` crossing module boundaries — define Pydantic models
- No `print()` in production code — use `logging` or `rich`
- No `time.sleep()` in async code — use `asyncio.sleep()`
- Tests for new logic — no PR adds untested public functions

---

## Adding a new LLM provider

This is the most common contribution. The architecture is designed for it:

1. Create `linkedin_intelligence/providers/myprovider.py`
2. Implement all methods of the `LLMProvider` Protocol defined in `providers/base.py`:
   - `extract_skills(job_description: str) -> ExtractedSkills`
   - `extract_recruiter_signals(message: str) -> dict[str, list[str]]`
   - `suggest_portfolio(stats: MarketStats, profile: UserProfile) -> str`
   - `infer_profile_domain(headline, role, skills) -> dict`
   - `health_check() -> bool`
3. Add a case to the factory in `providers/__init__.py`
4. Add required env vars to `.env.example` with clear comments
5. Add tests in `tests/unit/test_providers.py` using `respx` to mock HTTP

No other files need to change. The Protocol enforces the contract at type-check time.

---

## Pull request checklist

Before opening a PR, verify:

- [ ] `make lint` passes with no errors
- [ ] `make test` passes with no failures
- [ ] New public functions have type hints and docstrings
- [ ] New env vars are documented in `.env.example`
- [ ] `data/sample/` or `tests/fixtures/` updated if needed
- [ ] No credentials, personal data, or real LinkedIn data committed
- [ ] PR description explains **what** changed and **why**

---

## Commit style

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add OpenAI provider adapter
fix: handle empty job descriptions in skills extractor
docs: update Ollama setup instructions
test: add unit tests for profile parser
chore: bump ruff to 0.4.0
```

---

## Questions

Open a [GitHub Discussion](https://github.com/nico150891/linkedin-intelligence/discussions)
or an issue tagged `question`.
