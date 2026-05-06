# anidb-launcher Workflow (gstack style)

This project follows a repeatable sprint loop:

1. Think
2. Plan
3. Build
4. Review
5. Test
6. Ship
7. Reflect

If you have gstack installed, use these commands in order:

1. `/office-hours` to sharpen the user problem and define the smallest valuable wedge.
2. `/plan-eng-review` to lock architecture, edge cases, and test scope.
3. Build the feature on a branch.
4. `/review` to catch production-risk issues before merge.
5. `/qa` for UI behavior checks on meaningful flows.
6. `/ship` for final release hygiene and PR readiness.
7. `/retro` to capture what to improve next cycle.

For UI-heavy changes, add this step between review and ship:

1. Run a design pass (`/design-review` style) and execute
   `docs/UI_REVIEW_CHECKLIST.md`.

If gstack is not available, keep the same order manually using this file as the checklist.

## Repo Quality Gates

Run these before opening or merging a PR:

1. `python -m pytest -q`
2. `python scripts/ship_check.py`
3. `python scripts/ship_check.py --include-build` (release builds only)

## Definition Of Done

- Feature behavior is validated with tests or documented manual QA steps.
- UI changes were checked against `DESIGN.md` and `docs/UI_REVIEW_CHECKLIST.md`.
- Source URL templates and defaults still validate.
- Existing tests pass.
- Release notes/changelog entry is drafted for user-facing changes.
- Packaging smoke check passes for release candidates.
