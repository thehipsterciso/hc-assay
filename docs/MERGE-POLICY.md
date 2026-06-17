# Merge policy — CI must be green before merge (#CI-1)

## The gap

CI defines an `all-checks` job that fans in `core`, `integration`, and `audit` and is designed to
be the single required status check. **But branch protection is unavailable on this repository's
plan** — it is private on a free tier, so the branch-protection API returns:

```
HTTP 403: Upgrade to GitHub Pro or make this repository public to enable this feature.
```

Consequently GitHub does **not** block merging a pull request whose CI is red. The `all-checks`
result is computed but nothing on the platform enforces it. This is the exact mechanism by which CI
ran silently red across several hardening passes (merge commits for #161/#162/#166/#167/#168 all show
`conclusion=failure`) — they were merged without a green gate.

## Why we don't just enable enforcement

- **Making the repo public** would enable branch protection, but it would also **publish the
  committed `transcripts/`** (agent provenance). That is out of scope and a data-sovereignty
  regression — do not do it to satisfy this gate.
- **Upgrading the plan** (GitHub Pro/Team) is an operator/billing decision, not a code change.

## The compensating control (mandatory)

Until protection is available, the merge gate is **procedural + scripted**:

1. Push the branch and let CI run.
2. Run `scripts/require_green_ci.sh [branch]` — it exits non-zero unless the latest `ci` run for the
   branch concluded `success`.
3. Merge **only** if that passes:

   ```sh
   scripts/require_green_ci.sh && gh pr merge <n> --merge --delete-branch
   ```

4. **Never** `--admin`-merge past a red `all-checks`. A red required check is a finding, not a
   nuisance — read why it failed and fix it first (this is how pass 8 found three CI-only defects
   that a code-only review missed).

When the repository moves to a plan/visibility that supports branch protection, configure `main` to
require the `all-checks` status check and this procedural control becomes redundant.
