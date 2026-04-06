#!/usr/bin/env bash
# scripts/init_repo.sh
#
# Run this ONCE after cloning or creating the project locally.
# Creates the GitHub repo, pushes main, and applies all configuration.
#
# Prerequisites:
#   - gh CLI installed and authenticated (gh auth status)
#   - git initialized with at least one commit
#
# Usage:
#   bash scripts/init_repo.sh

set -euo pipefail

OWNER="nico150891"
REPO="linkedin-intelligence"
FULL_REPO="$OWNER/$REPO"

# ── Checks ────────────────────────────────────────────────────────────────────
echo "🔍 Checking prerequisites..."

if ! command -v gh &>/dev/null; then
  echo "❌ gh CLI not found. Install from https://cli.github.com/"
  exit 1
fi

if ! gh auth status &>/dev/null; then
  echo "❌ gh CLI not authenticated. Run: gh auth login"
  exit 1
fi

if ! git rev-parse --git-dir &>/dev/null; then
  echo "❌ Not a git repo. Run: git init && git add . && git commit -m 'chore: initial skeleton'"
  exit 1
fi

echo "✓ All prerequisites met"

# ── Create repo ───────────────────────────────────────────────────────────────
echo ""
echo "📦 Creating GitHub repo..."

if gh repo view "$FULL_REPO" &>/dev/null 2>&1; then
  echo "  Repo already exists — skipping creation"
else
  gh repo create "$FULL_REPO" \
    --public \
    --source=. \
    --remote=origin \
    --description "Analyze the LinkedIn job market from your own data. Extract skill trends and generate portfolio project suggestions — powered by your choice of LLM."
  echo "✓ Repo created: https://github.com/$FULL_REPO"
fi

# ── Push main ─────────────────────────────────────────────────────────────────
echo ""
echo "🚀 Pushing to main..."

git push -u origin main
echo "✓ main pushed"

# ── Configure repo ────────────────────────────────────────────────────────────
echo ""
bash scripts/setup_github.sh

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Repo ready: https://github.com/$FULL_REPO"
echo ""
echo "Next steps:"
echo "  1. make install            install dependencies"
echo "  2. playwright install chromium"
echo "  3. cp .env.example .env    fill in your API keys"
echo "  4. make sample-run         verify everything works"
echo "  5. pre-commit install      enable git hooks"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
