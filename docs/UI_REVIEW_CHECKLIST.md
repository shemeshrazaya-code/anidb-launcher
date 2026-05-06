# UI Review Checklist - anidb-launcher

Use this before merge for UI-facing changes and before release builds.

## 1) First Impression (10-20 seconds)

- The page purpose is immediately obvious.
- Primary actions are visible without hunting.
- No obvious clipping, overlap, or broken layout at initial window size.
- Theme toggle label is correct for the current state.

## 2) Layout and Hierarchy

- App bar content stays aligned and readable.
- Card grid and detail panel feel balanced at default size.
- Heading, title, metadata, and helper text follow visual hierarchy.
- Empty states are clear and not visually noisy.

## 3) Discovery Flow (Browse -> Select -> Launch)

- Search input focus works via `Ctrl+F` and `/`.
- Typing in search does not cause visible jank or freeze.
- Card hover and selected states are consistent and obvious.
- Clicking a card always updates the detail panel correctly.
- Launch action is easy to find and behaves as expected.

## 4) Filters and Sorting

- Filter controls are readable in both dark and light themes.
- `Reset filters` returns to a known default state.
- Favorites-only toggle clearly reflects active state.
- Sort choice updates list order as expected.

## 5) Theme Quality (Dark and Light)

- Background/text contrast is readable in both themes.
- Card borders remain visible but not noisy.
- Selected card remains clearly distinguishable.
- Badges and metadata remain legible after theme switch.
- Theme switch does not leave stale colors in cards/source rows.

## 6) Content Quality

- Long titles are truncated or wrapped gracefully.
- Synopsis area remains readable and does not overflow container.
- Missing fields do not produce awkward blank gaps or placeholder artifacts.
- Source availability statuses are understandable at a glance.

## 7) Responsiveness and Resize

- Resize wide -> narrow -> wide without layout corruption.
- Card columns reflow smoothly (no thrashing/flicker).
- Detail panel remains usable at minimum supported size.
- Scrollbars appear and behave correctly where needed.

## 8) Input, Focus, and Keyboard

- Focus ring/behavior is predictable after dialogs close.
- Tab order reaches major controls logically.
- Enter/Space do not trigger unexpected actions in focused widgets.
- Mouse wheel scrolling works only in the intended region.

## 9) Stability and Error Handling

- Thumbnail loading failures show graceful fallback text/state.
- Slow network does not block typing or UI interactions.
- Source checks can fail per-row without breaking the entire view.
- Error text is human-readable and not stack-trace-like.

## 10) Release Candidate Signoff

- Capture at least one screenshot per theme for changed areas.
- Run `python scripts/ship_check.py`.
- For release builds run `python scripts/ship_check.py --include-build`.
- Record any accepted UI debt in the PR notes.

