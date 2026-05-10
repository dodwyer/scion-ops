# Proposal: Web UI Theme

## Summary

Define a basic operational theme for the scion-ops web UI. The interface should read as a professional monitoring console for live Scion state: restrained, dense enough for repeated operator use, clear under degraded conditions, and free of marketing or decorative dashboard styling.

## Motivation

The web app now surfaces live Hub, MCP, Kubernetes, OpenSpec, branch, validation, and final-review state. Operators need to scan this information while rounds are active, blocked, stale, or waiting on review. A decorative or presentation-heavy theme would compete with the operational data and make status changes harder to notice.

A shared theme contract gives implementation rounds concrete guidance for visual hierarchy, color use, spacing, typography, and state treatment without changing the app's read-only source-of-truth behavior.

## Scope

In scope:

- Establish a restrained visual theme for the existing overview, rounds, round detail, inbox, runtime, and live-update surfaces.
- Define semantic color treatment for healthy, running, waiting, stale, degraded, blocked, failed, and unavailable states.
- Improve readability for dense operational tables, timeline entries, metadata pills, code-like values, and source error panels.
- Preserve the current read-only app behavior and existing information architecture.
- Require responsive behavior that keeps monitoring usable on narrow screens without overlapping text or controls.

Out of scope:

- Adding new write operations or workflow controls.
- Replacing the web app framework or backend adapter.
- Changing MCP, Hub, Kubernetes, OpenSpec, or live-update data contracts.
- Adding a marketing landing page, decorative illustrations, or non-operational dashboard widgets.
- Introducing production authentication or multi-user personalization.

## Success Criteria

- Operators can quickly distinguish healthy, running, waiting, stale, degraded, blocked, failed, and unavailable states across all web app views.
- The theme uses a restrained neutral foundation with limited semantic accents and avoids ornamental gradients, oversized hero treatment, and decorative card layouts.
- Dense tables, metadata, timelines, branch values, validation details, and JSON/code blocks remain legible during repeated monitoring.
- The app remains responsive without text or controls overlapping on typical desktop and mobile widths.
- Theme implementation is covered by focused fixture, static, or visual checks that do not start model-backed rounds.
