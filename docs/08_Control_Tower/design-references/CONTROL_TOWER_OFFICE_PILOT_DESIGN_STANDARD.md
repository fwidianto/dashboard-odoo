# Control Tower Office Pilot Design Standard

Status: implementation reference for the frozen Office Pilot Readiness campaign.

## Purpose and boundary

This standard keeps the accepted Warm Amber three-panel Control Tower recognizable while making the shared 1920 × 1080 office view readable and calm. It covers the overview and dedicated Temuan worklist only. It does not redesign the existing dashboard family or add workflow actions.

## Visual language

- Font: `Inter` when installed, then the existing system UI fallback stack.
- Page: Warm Amber background `#f4eee5`; primary surface `#fffdf9`; soft surface `#fbf6ee`.
- Text: primary `#30291f`; muted `#7d7161`; borders `#ddcfbb`.
- Accent: amber `#d98e26`; strong amber `#a96312`; pale amber `#fff3de`.
- Semantic states: success `#4f7a5a`; warning `#c77d1a`; critical/error `#a94b2b`; in-progress blue-gray `#5c7c9a`.

## Type and spacing

| Use | Size | Guidance |
| --- | ---: | --- |
| Page title | 24–38 px | Use once per surface. |
| Panel heading | 18–20 px | Keep the business noun visible. |
| Office-screen body | 12–13 px | Do not go below 12 px for essential meaning at 100% zoom. |
| Supporting metadata | 10–11 px | Use for timestamps, rule IDs, and limitations. |
| Minimum interactive target | 36 px high | Native buttons and links remain keyboard reachable. |
| Spacing scale | 7 / 10 / 14 / 18 / 28 px | Avoid one-off spacing values. |

## Office layout

- Target viewport: 1920 × 1080 at 100% browser zoom.
- Default identity: left Temuan summary, center Process Map, right Process Inspector.
- Desktop grid: approximately 252 px / flexible center / 292 px, with a 16 px gap.
- At the target desktop width, the default Process Map canvas is constrained to 1090 px so the primary spine does not require horizontal scrolling.
- `Fokus Process Map` temporarily hides the side panels and gives the map the full center width. The control returns to the three-panel identity.
- Narrower screens may use a scroll cue or a single-column layout; this is not evidence of office-display readiness.
- No debug controls, development overlays, or raw credentials belong on the display.

## Component rules

- Finding cards show category, rule/status/severity context, evidence wording, and only a supported destination.
- The inspector shows source evidence and limitations before any interpretation.
- Counts come from the server response. API/database failure uses `Belum tersedia` or an explicit error, never fabricated zeroes.
- Unsupported destinations say so plainly; they are not rendered as dead links.
- Selected cards use the amber border/pale amber surface and retain keyboard focus visibility.

## Freshness and failure states

The freshness banner must keep the exact trusted completion timestamp visible and use these presentation states:

- `CURRENT`: trusted snapshot age is no more than 24 hours.
- `STALE`: trusted snapshot age is more than 24 hours and no more than 48 hours.
- `CRITICALLY_STALE`: trusted snapshot age is more than 48 hours, or no trusted completed snapshot exists.
- `REFRESHING`: an active or publish-ready attempt exists; the previous trusted snapshot remains the displayed source.
- `FAILED`: the latest attempt failed/aborted, or the health service cannot be read. The previous trusted snapshot remains visible when available.

Empty, loading, API-unavailable, database-unavailable, and unsupported states must remain visually distinct. A failed service is not an empty worklist.

## Motion

- Routine transitions: 150–250 ms.
- Panel transitions: 200–300 ms.
- Process-flow motion: one calm 2–4 second cycle.
- No bouncing, decorative glow, constant pulsing, or repeated visible animation restart.
- `prefers-reduced-motion: reduce` disables flow animation and reduces transitions to effectively none.

## Correct and incorrect examples

| Correct | Incorrect |
| --- | --- |
| `STALE` plus the trusted completion timestamp and age | A stale snapshot styled as `CURRENT` |
| `FAILED` plus the last trusted snapshot and recovery guidance | Replacing the list with zero counts after a database error |
| “No exact compatible investigation page is available” | A link that guesses a document destination |
| Focused map with a visible return control | A shared screen left on one user’s selected finding forever |
| Native controls with 36 px targets and focus rings | Mouse-only custom controls or hidden selection state |
