# Security Policy

## Supported Versions

This is a personal portfolio project. Only the latest version on `main` receives attention.

| Version | Supported |
|---|---|
| latest (`main`) | ✅ |
| older tags | ❌ |

---

## Data Handling & Privacy

This project processes sensitive personal data. Understanding what goes where is important:

### What stays on your machine (never leaves)
- LinkedIn credentials (`LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD`) — stored only in `.env`, gitignored
- Your GDPR export (`data/raw/gdpr_export/`) — gitignored, never committed
- Processed data (`data/processed/`) — gitignored, never committed
- Output reports (`output/`) — gitignored, never committed
- Playwright session cookies (`data/raw/.session`) — gitignored, never committed

### What leaves your machine
- Job descriptions from LinkedIn's public job search pages → sent to your configured LLM provider (DeepSeek, Anthropic, or Ollama)
- Recruiter message text (if using message analysis) → sent to your configured LLM provider
- If using **Ollama**: nothing leaves your machine — all LLM calls are local

### What is committed to this public repo
- Only synthetic sample data in `data/sample/` — fully fictional, no real personal information
- No credentials, no real messages, no real job applications

---

## Recommendations Before Using This Project

1. **Review your `.gitignore`** before the first commit — verify `data/raw/`, `data/processed/`, `output/`, and `.env` are listed
2. **Use Ollama** if you want zero data leaving your machine
3. **Review the LLM provider's privacy policy** if using DeepSeek or Anthropic
4. **Do not share your `.env` file** or the contents of `data/raw/` with anyone

---

## Reporting a Vulnerability

This project doesn't handle third-party user data, so the attack surface is limited.
If you find a security issue (e.g. a code path that could leak credentials or personal data):

1. **Do not open a public GitHub issue**
2. Contact me directly via GitHub: [@nico150891](https://github.com/nico150891)
3. Describe the issue and steps to reproduce
4. I'll respond within 7 days

---

## Out of Scope

- Issues with LinkedIn's own platform or API
- Issues with your LLM provider (DeepSeek, Anthropic, Ollama)
- General Python dependency vulnerabilities unrelated to data handling
