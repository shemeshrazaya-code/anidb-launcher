# Design System - anidb-launcher

## Product Context

- What this is: Desktop launcher for browsing ranked anime and opening user-configured search sources.
- Audience: Anime users who want fast browse -> search workflows, not in-app streaming.
- Platform: Tkinter desktop app (Windows-first polish, cross-platform support).
- Core promise: Fast scanning, low-friction launching, and predictable behavior.

## Design Principles

1. Scan first, read second.
- Users should be able to find a title visually from card layout, cover art, rating, and short metadata.

2. Minimize thinking cost.
- Primary actions must stay obvious: search/filter, select, launch, favorite, remind.

3. Keep interaction latency low.
- Perceived speed is part of design quality. Avoid full-grid reflows and blocking UI work.

4. Respect desktop conventions.
- Keyboard focus, scroll behavior, split panes, and dialog actions should feel native.

## Information Architecture

- App bar:
- Brand/title, mode badge, refresh, theme toggle.
- Browse area:
- Left: card grid for discovery.
- Right: detail panel for decision-making and actions.
- Utility views:
- Favorites and reminders preserve the same visual language and row structure.

## Visual System

## Color + Theme

- Theme modes: `dark` and `light`.
- Tokens live in `App._THEMES` in [anidb_launcher/ui.py](C:\Users\BC\anidb-launcher\anidb_launcher\ui.py).
- Use tokens, not hardcoded colors, for new UI surfaces.
- Primary card states:
- Default (`card_border`, base bg)
- Hover (`card_hover_bg`, `card_hover_border`)
- Selected (`card_selected_bg`, `card_selected_border`)

## Typography

- Primary family: `Segoe UI` (already used across UI labels and controls).
- Hierarchy:
- App title: 16 bold
- Section headers: 14 bold
- Card title/detail title: 10 bold
- Supporting metadata: 8-10 regular
- Rule: preserve this hierarchy ratio unless a global revision is intentional.

## Spacing + Density

- Use 4px/6px/8px/12px increments already present in layouts.
- Cards should remain dense but readable; avoid vertical bloat in metadata lines.
- Keep action rows compact and scannable.

## Component Guidelines

## Cards

- Card background and border must reflect hover/selected states consistently.
- Thumbnail + title + minimal metadata should remain visible without click.
- Reflows should be debounce-controlled (see `_schedule_card_relayout`).

## Detail Panel

- Keep synopsis readable with stable wrap width and high contrast.
- Action buttons should stay in a predictable location relative to title/rating.
- Source availability chips should read as status, not primary CTA.

## Filters + Search

- Search entry is primary input; keep keyboard-first behavior (`Ctrl+F`, `/`).
- Filters should avoid hidden dependencies; reset must return to known defaults.

## Motion and Responsiveness

- Prefer subtle state changes (hover, selection, loading text swap), not decorative animation.
- Keep heavy work off main thread:
- Thumbnails use worker threads + UI queue.
- Grid updates are debounced to prevent typing/resize jank.

## Accessibility and Usability Baseline

- Maintain clear contrast for title/meta text in both dark and light themes.
- Ensure selected card state is distinguishable by more than color whenever possible (border + bg delta).
- Preserve keyboard discoverability for search and list navigation behavior.
- Avoid tiny hit targets for key actions.

## Performance-Sensitive UI Rules

- No synchronous network calls on main thread.
- No full list rebuild on every keystroke unless no safe incremental option exists.
- Re-render only changed surfaces on theme swap where possible.

## Design Review Workflow

- Use [docs/UI_REVIEW_CHECKLIST.md](C:\Users\BC\anidb-launcher\docs\UI_REVIEW_CHECKLIST.md) for each release candidate.
- Capture findings with:
- Observation: what is happening
- Impact: why it matters
- Fix: smallest safe change

## Decisions Log

Add entries here when making intentional visual-system changes.

| Date | Decision | Reason | Files |
|---|---|---|---|
| 2026-05-06 | Initial project design system document | Establish shared visual and UX rules for consistent iteration | `DESIGN.md`, `docs/UI_REVIEW_CHECKLIST.md` |

