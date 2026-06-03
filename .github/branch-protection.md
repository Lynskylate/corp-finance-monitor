# Branch Protection Configuration

Manual steps to configure in the GitHub repository settings.
Go to: Settings → Branches → Add rule → Branch name pattern: `main`

## Required Rule

| Setting | Value | Rationale |
|---------|-------|-----------|
| Branch name pattern | `main` | Protect the canonical trunk |
| Require a pull request before merging | ✅ | All changes via PR |
| └─ Require approvals | `1` | At least one reviewer sign-off |
| └─ Dismiss stale reviews when new commits are pushed | ✅ | New commits invalidate old approvals |
| Require status checks to pass before merging | ✅ | CI must be green |
| └─ Require branches to be up to date before merging | ✅ | Prevents merging stale branches that pass CI but conflict with newer main |
| Require conversation resolution before merging | ✅ | All review threads resolved |
| Do not allow bypassing the above settings | ✅ | Admins must follow rules too |
| Allow force pushes | ❌ | Linear history only |
| Allow deletions | ❌ | Protect branch from deletion |

## Required Status Checks

After configuring the rule above, select these checks from the CI workflow:

| Check | Job | Purpose |
|-------|-----|---------|
| `lint` | Python lint + format | Catch style/import/typing issues |
| `frontend` | ESLint + tsc + vite build | Catch frontend regressions |
| `test (3.10)` | Python 3.10 test matrix | Minimum supported Python |
| `test (3.11)` | Python 3.11 test matrix | |
| `test (3.12)` | Python 3.12 test matrix | Current target Python |
| `build` | Wheel + sdist build | Verify package builds (depends on lint + test passing) |

## How This Prevents "Old Branch Behind Main" Problems

1. **Branch up-to-date**: PRs cannot merge if the branch is behind `main`. This forces rebase/merge from `main` before merging, ensuring the merged state is actually tested.
2. **Required CI checks**: Local `make gate` mirrors CI checks — developers can verify before pushing.
3. **Review gate**: At least one human reviewer must approve, catching logic-level issues CI can't.

## Setup Instructions

1. Go to `https://github.com/<owner>/corp-finance-monitor/settings/branches`
2. Add branch protection rule for `main` with the settings above
3. After the first CI run on a PR, the check names will appear in the "Status checks" search — search for `lint`, `frontend`, `test`, `build` and select them
4. Verify by opening a test PR — it should show all checks as required

## Things NOT Locked Down (intentional)

- **No minimum PR description template**: Lightweight for small fixes; use reviewer discretion
- **No CODEOWNERS**: Team is small, anyone can review
- **No merge queue**: Good for later, but adds complexity; current linear merge model is sufficient
