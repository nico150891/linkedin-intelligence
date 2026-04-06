#!/usr/bin/env bash
# scripts/setup_github.sh
#
# Configures the GitHub repo after creation:
#   - Description and topics
#   - Branch protection on main
#   - Disables unused GitHub features
#
# Requires: gh CLI authenticated (`gh auth status`)
# Usage: bash scripts/setup_github.sh

set -euo pipefail

OWNER="nico150891"
REPO="linkedin-intelligence"
FULL_REPO="$OWNER/$REPO"

echo "🔧 Configuring $FULL_REPO..."

# ── 1. Repo metadata ─────────────────────────────────────────────────────────
echo "→ Setting description and topics..."

gh repo edit "$FULL_REPO" \
  --description "Analyze the LinkedIn job market from your own data. Extract skill trends and generate portfolio project suggestions — powered by your choice of LLM." \
  --enable-issues \
  --enable-wiki=false \
  --enable-projects=false \
  --delete-branch-on-merge

gh api "repos/$FULL_REPO/topics" \
  --method PUT \
  --input - <<'EOF'
{"names":["python","linkedin","cli","llm","playwright","data-analysis","portfolio","deepseek","ollama","job-market"]}
EOF

echo "✓ Metadata configured"

# ── 2. Branch protection on main ─────────────────────────────────────────────
echo "→ Configuring branch protection on main..."

gh api "repos/$FULL_REPO/branches/main/protection" \
  --method PUT \
  --header "Accept: application/vnd.github+json" \
  --input - <<'EOF'
{
  "required_status_checks": {"strict": true, "contexts": ["lint", "test"]},
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false
}
EOF

echo "✓ Branch protection configured"
echo ""
echo "  Rules applied to main:"
echo "  • PR required before merge (1 approval, code owner review)"
echo "  • CI checks must pass (lint + test)"
echo "  • Stale reviews dismissed on new commits"
echo "  • Force pushes blocked"
echo "  • Branch deletion blocked"
echo "  • enforce_admins=false → you can still push directly as admin"

# ── 3. Summary ────────────────────────────────────────────────────────────────
echo ""
echo "✅ GitHub setup complete."
echo "   Repo: https://github.com/$FULL_REPO"
echo ""
echo "⚠️  Reminder: docs/BRANCH_PROTECTION.md has the manual steps"
echo "   in case you need to adjust anything in GitHub Settings UI."
