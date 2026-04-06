# Branch Protection Setup

This file documents the branch protection configuration for `main`.
**This must be configured manually in GitHub Settings — it cannot be automated via files.**

## Steps to configure

1. Go to: `https://github.com/nico150891/linkedin-intelligence/settings/branches`
2. Click **Add branch ruleset** (or "Add rule" in classic interface)
3. Configure as follows:

### Ruleset name
```
protect-main
```

### Target branches
```
main
```

### Rules to enable

```
✅ Restrict deletions
   → Prevents anyone from deleting the main branch

✅ Require a pull request before merging
   ├── Required approvals: 1
   ├── ✅ Dismiss stale pull request approvals when new commits are pushed
   └── ✅ Require review from Code Owners (optional, skip if no CODEOWNERS file)

✅ Require status checks to pass
   ├── ✅ Require branches to be up to date before merging
   └── Add status checks: "lint", "test"
       (these match the job names in .github/workflows/ci.yml)

✅ Block force pushes

❌ Do NOT enable "Do not allow bypassing the above settings"
   → Leaving this OFF means YOU (as admin) can still push directly to main
   → Everyone else must go through a PR
```

## Result

- Contributors: must fork → branch → PR → wait for your approval
- You (admin): can push directly to main OR use PRs — your choice
- CI must pass before any PR can be merged (lint + unit tests)
- Nobody can force-push or delete main

## CODEOWNERS (optional but recommended)

Create `.github/CODEOWNERS` with:
```
* @nico150891
```

This means every PR automatically requests your review.
With "Require review from Code Owners" enabled, GitHub enforces it.
