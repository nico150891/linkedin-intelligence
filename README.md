# linkedin-intelligence

> Analyze the LinkedIn job market from your own data. Extract skill trends, industry signals,
> and generate prioritized portfolio project suggestions — powered by your choice of LLM.

[![CI](https://github.com/nico150891/linkedin-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/nico150891/linkedin-intelligence/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)

<!-- demo.gif goes here once recorded with asciinema -->

---

## Why I built this

As a Head of AI actively navigating the job market, I wanted a data-driven answer to a question
I kept asking myself: *what should I build next to stay relevant?*

Most portfolio advice is generic. This tool answers it with your actual market —
scraping the jobs you'd realistically apply to, analyzing recruiter messages you've already
received, and using an LLM to connect the dots into concrete project suggestions.

It also ended up being a good excuse to build something production-grade with a pluggable
LLM backend, async pipelines, and proper observability — things that matter in real AI engineering roles.

---

## What it does

1. **Detects your profile** from your LinkedIn GDPR export — infers your domain and auto-suggests search keywords
2. **Scrapes job listings** from LinkedIn based on your role and location
3. **Parses recruiter messages** from your inbox as an additional market signal
4. **Extracts structured skill data** from each job description using an LLM of your choice
5. **Produces market statistics** — top skills, technologies, industries, seniority distribution
6. **Suggests portfolio projects** personalized to your profile and prioritized by market demand

All processing runs locally or via cheap API calls (~$0.15 for 350 jobs with DeepSeek).
No third-party data brokers. Your data stays on your machine.

---

## Architecture

```
GDPR Export ─── Profile.csv + Positions.csv + Skills.csv
                         │
                         ▼
                   UserProfile (domain, suggested keywords)
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
  messages.csv                  LinkedIn Jobs (Playwright)
  connections.csv                        │
  job_applications.csv                   │
          │                             │
          ▼                             ▼
    data/raw/  ──────────────────► data/processed/
                                         │
                                         ▼
                               SkillsExtractor (batched, incremental)
                                         │
                              ┌──────────┴──────────┐
                              │    LLMProvider       │
                              │    (pluggable)       │
                         DeepSeek  Ollama  Anthropic
                              │                      │
                              └──────────┬───────────┘
                                         │
                                    analysis/
                                         │
                              ┌──────────┴──────────┐
                              ▼                      ▼
                         stats.json     portfolio_suggestions.md
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full data flow diagram with schemas.

---

## Features

- **Profile-aware** — detects your professional domain from GDPR data; personalizes keywords and suggestions
- **Pluggable LLM backend** — swap DeepSeek, Ollama, or Anthropic via one env variable, no code changes
- **Incremental runs** — skips already-processed jobs; safe to re-run without wasting tokens
- **Recruiter signal analysis** — extracts skills and roles from inbound recruiter messages
- **Rich progress bars** — real-time feedback, critical for Ollama runs (60–90 min on CPU)
- **Privacy-first** — raw data and credentials are gitignored; only synthetic sample data is committed
- **Type-safe** — `mypy --strict` passes clean; Pydantic v2 validates all LLM responses
- **Resilient pipeline** — per-job failures are logged and skipped; the batch never breaks
- **Sample run** — full pipeline demo with synthetic data, no credentials needed

---

## Quick start

### Prerequisites

- Python 3.12+
- Docker (only if using Ollama)
- `gh` CLI (only for repo setup)

### Installation

```bash
git clone https://github.com/nico150891/linkedin-intelligence.git
cd linkedin-intelligence
pip install -e ".[dev]"
playwright install chromium
cp .env.example .env
```

### Try it without credentials

```bash
make sample-run
```

Runs the full pipeline against `data/sample/` (synthetic data) and writes results to `output/`.
No LinkedIn account or API key needed.

### Full pipeline with your data

**Step 1 — Get your GDPR export**

LinkedIn → Settings → Data Privacy → Get a copy of your data.
Unzip into `data/raw/gdpr_export/`.

**Step 2 — Configure `.env`**

```bash
LLM_PROVIDER=deepseek        # or "ollama" or "anthropic"
DEEPSEEK_API_KEY=your_key
LINKEDIN_EMAIL=your@email.com
LINKEDIN_PASSWORD=your_password
```

**Step 3 — Run**

```bash
linkedin-intel run-all --location "Spain"
# Auto-detects your profile and suggests keywords,
# or pass them manually: --keywords "ML engineer" "AI engineer"
```

Results → `output/stats.json` and `output/portfolio_suggestions.md`.

---

## LLM Providers

| Provider | Config needed | Cost (350 jobs) | Speed |
|---|---|---|---|
| `deepseek` ⭐ | `DEEPSEEK_API_KEY` | ~$0.15 | ~2 min |
| `ollama` | Docker | Free | ~60–90 min CPU |
| `anthropic` | `ANTHROPIC_API_KEY` | ~$1.80 | ~4 min |

```bash
# Switch providers with no code changes
LLM_PROVIDER=ollama  # in .env

# Ollama setup
make ollama-up                   # pulls qwen2.5:7b, starts container
linkedin-intel test-provider     # verify it's working
```

---

## CLI reference

```bash
linkedin-intel run-all           # full pipeline (profile → scrape → extract → analyze)
linkedin-intel parse-profile     # detect UserProfile from GDPR export
linkedin-intel parse-gdpr        # parse messages, connections, job applications
linkedin-intel scrape-jobs       # scrape LinkedIn job listings
linkedin-intel extract-skills    # extract skills from job descriptions via LLM
linkedin-intel analyze           # generate stats.json + portfolio_suggestions.md

# Flags
--location "Spain"               # target location for job search
--keywords "ML engineer" "..."   # override auto-detected keywords
--since 2025-01-01               # only scrape jobs published after this date
--dry-run                        # simulate scraping without making requests

# Utilities
linkedin-intel test-provider     # health check the configured LLM provider
linkedin-intel sample-run        # full pipeline with synthetic data
```

---

## Development

```bash
make install      # pip install -e ".[dev]"
make lint         # ruff + mypy --strict
make format       # ruff format (applies changes)
make test         # unit tests — no external calls
make test-cov     # with coverage report
make test-ollama  # integration: 1 real job against Ollama
make ci           # lint + test (mirrors GitHub Actions)
make clean        # remove caches and build artifacts
```

### Adding a new LLM provider

1. Create `linkedin_intelligence/providers/myprovider.py`
2. Implement the `LLMProvider` Protocol from `providers/base.py`
3. Add a case to the factory in `providers/__init__.py`
4. Document env vars in `.env.example`
5. Add tests in `tests/unit/test_providers.py` using `respx`

No other files need to change. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for full details.

---

## Output example

**`output/stats.json`**
```json
{
  "top_tecnologias": [
    {"name": "Python", "count": 287, "pct": 82.0},
    {"name": "Docker", "count": 201, "pct": 57.4},
    {"name": "PyTorch", "count": 178, "pct": 50.9}
  ],
  "seniority": {"mid": 0.48, "senior": 0.35, "junior": 0.17},
  "remote_pct": 0.63,
  "recruiter_signals": {
    "top_mentioned_roles": ["ML Engineer", "AI Lead", "Head of AI"],
    "inbound_recruiter_count": 23
  }
}
```

**`output/portfolio_suggestions.md`**
```markdown
# Portfolio Suggestions for Nicolás Leiva
*Head of AI · Based on 350 job listings + 23 recruiter messages analyzed*

## 1. Production LLM Gateway with FastAPI + LiteLLM
**Stack:** Python, FastAPI, LiteLLM, Redis, Docker
**Market signal:** LLM deployment appears in 71% of listings
**Why for you:** bridges your LLM expertise with the MLOps gap most roles require
**Difficulty:** Medium — 2–3 weekends
```

---

## Troubleshooting

**`Error: LinkedIn session expired`**
```bash
rm data/raw/.session
linkedin-intel scrape-jobs  # will open browser for manual login
```

**`Error: Provider health check failed`**
```bash
# Ollama not running?
make ollama-up

# Wrong API key?
linkedin-intel test-provider  # prints the exact error
```

**`Error: GDPR export not found`**
```bash
# Check the path — must be unzipped, not the .zip
ls data/raw/gdpr_export/   # should contain .csv files
# If empty: set GDPR_EXPORT_PATH in .env to the correct path
```

**`extract-skills processes 0 jobs`**
```bash
# All jobs already processed — run scrape-jobs first to get new ones
linkedin-intel scrape-jobs --location "Spain" --since 2025-01-01
```

**`mypy errors on install`**
```bash
# Make sure you installed dev dependencies
pip install -e ".[dev]"
```

---

## Data & privacy

- `data/raw/`, `data/processed/`, `output/` → gitignored, never committed
- `.env` → gitignored, credentials never leave your machine
- `data/sample/` → fully synthetic data, safe for public repos
- LLM providers receive job descriptions only — no credentials, no personal messages unless you enable recruiter analysis

See [`SECURITY.md`](SECURITY.md) for full details.

---

## Roadmap

- [ ] `asciinema` demo recording
- [ ] Web dashboard (FastAPI + minimal frontend)
- [ ] Support for Indeed and Glassdoor
- [ ] Scheduled weekly runs with delta detection
- [ ] Skill gap analysis against your declared LinkedIn profile skills

---

## Contributing

PRs welcome. The `main` branch is protected — all changes require a pull request and explicit approval.
See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the workflow and code standards.

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built by [Nicolás Leiva](https://github.com/nico150891)*
