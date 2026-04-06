# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Initial project skeleton and documentation

---

## [0.1.0] — TBD

### Added
- `parse-profile` — detects `UserProfile` from GDPR export (role, domain, skills, suggested keywords)
- `parse-gdpr` — parses messages, connections, and job applications from LinkedIn GDPR export
- `scrape-jobs` — async Playwright scraper with session persistence, retry, and rate limiting
- `extract-skills` — batched LLM extraction with incremental cache (skips already-processed jobs)
- `analyze` — generates `stats.json` and personalized `portfolio_suggestions.md`
- `run-all` — full pipeline in one command
- `sample-run` — full demo with synthetic data, no credentials needed
- Pluggable LLM backend: DeepSeek (default), Ollama (local), Anthropic
- Recruiter message signal analysis integrated into market stats
- Rich progress bars for long-running extractions
- GitHub Actions CI: lint (`ruff` + `mypy --strict`) + unit tests on every push
- Synthetic sample data in `data/sample/` for tests and demo

[Unreleased]: https://github.com/nico150891/linkedin-intelligence/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/nico150891/linkedin-intelligence/releases/tag/v0.1.0
