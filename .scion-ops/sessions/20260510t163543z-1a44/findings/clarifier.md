# Spec Clarifier Findings: web-ui-theme

**Session**: 20260510t163543z-1a44  
**Change**: web-ui-theme  
**Date**: 2026-05-10

---

## Goal Restatement

Apply a professional, operator-focused visual theme to the Scion web UI. The UI is a read-only monitoring dashboard rendered as a single embedded HTML/CSS/JS page in `scripts/web_app_hub.py`. The theme should serve operators who may be watching live system state for extended periods.

---

## Current State Summary

The UI already has a coherent light theme using CSS custom properties in a single `:root` block. Key characteristics:

- **Colors**: Light page background (`#f7f7f5`), white panels, dark text, muted grays, semantic status colors (green/orange/red/blue)
- **Typography**: `system-ui` at 14px / 1.45 line-height; `ui-monospace` at 12px for code
- **Components**: Cards, status badges, tables, timeline, decision flow, agent cards, code blocks
- **No external dependencies**: No framework, no CDN, no build step — everything is inline in the Python file

The existing palette is already restrained and functional. This change is an incremental refinement, not a ground-up redesign.

---

## Assumptions

1. **Scope is CSS-only**: The theme change touches only visual presentation (colors, typography, spacing, visual weight) — not layout structure, component composition, or data model.
2. **Single file**: All changes land in `scripts/web_app_hub.py` within the embedded `<style>` block. No new files.
3. **No external fonts or assets**: Consistent with the current no-dependency approach.
4. **Status colors are semantically load-bearing**: The good/warn/bad/info palette must remain distinguishable and accessible. Hue shifts are acceptable; semantic reversal is not.
5. **Responsive breakpoint is out of scope**: The 800px media query is structural, not thematic.

---

## Unresolved Questions

### 1. Dark vs. light mode — which baseline?

The current UI is light. Operators in NOC/ops environments commonly prefer dark themes (reduced eye strain, better contrast for status indicators against a dark field). The goal description does not specify.

**Options**:
- A: Refine the existing light theme (lower contrast, tighter palette, professional neutral tones)
- B: Replace with a dark theme (dark background, muted midtones, high-contrast status colors)
- C: Provide both via `prefers-color-scheme` media query

*Recommendation*: Option B (dark). A monitoring interface used by operators in real-time benefits most from a dark baseline — it reduces ambient light and makes status color pop more clearly. Option C adds complexity for a "basic" theme task.

### 2. How much typographic change is in scope?

The current font stack (`system-ui`) is already appropriate. Possible refinements:
- Tighter line-height for dense information scanning
- Slightly larger base font (15px) for readability on high-res displays
- Heavier heading weight

Is typography in scope, or is color/contrast the primary deliverable?

### 3. Information density: stay or adjust?

Current padding/spacing is comfortable (12px card padding, 8px gaps). Operators often prefer denser layouts. Should spacing be tightened, or preserved as-is?

### 4. What defines "done"?

Is the acceptance criterion:
- A: CSS variables updated, visual appearance changes, no functional regression
- B: A specific design reference or mockup to match
- C: Sign-off from a named reviewer

---

## Non-Goals (Inferred)

- No structural/layout changes
- No new UI features or data views
- No external dependencies (fonts, icon libraries, CSS frameworks)
- No changes to the Python server logic or API endpoints
- No mobile-first redesign (responsive breakpoint preserved as-is)

---

## Recommended Change Name

`web-ui-operator-theme`

Rationale: "theme" alone is generic; the qualifier "operator" anchors the intent and distinguishes it from a decorative or branding-driven theme change.

---

## Recommended Implementation Scope

Minimal viable scope to satisfy the goal:

1. Update `:root` CSS variables (background, panel, text, muted, line, status colors)
2. Adjust `color-scheme` declaration if switching to dark
3. Update `.mono` code block colors if palette changes
4. Update `.reason-box` and `.error-box` tinted backgrounds to match new palette
5. Optionally tighten `font-size`/line-height

All changes confined to the `<style>` block in `scripts/web_app_hub.py`.
