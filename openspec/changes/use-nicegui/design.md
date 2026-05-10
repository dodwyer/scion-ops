# Design: Use NiceGUI

## Overview

The web UI should be rebuilt as a NiceGUI application that presents scion-ops state as an operator console. The implementation should keep the server-side Python boundary and source adapters, but the visible UI should be rethought around operator tasks rather than mirroring the current structure.

The default experience should answer three questions quickly:

- Is the control plane usable right now?
- Which rounds need attention?
- Where is the next useful context if something is blocked, stale, or failed?

Deep diagnostics remain available, but they should be one level down from the default overview through tabs, drawers, expandable rows, detail panes, or drill-in views.

## NiceGUI Application Shape

The replacement should use NiceGUI for page composition, navigation, interactive controls, and live UI updates. It should remain Python-native and avoid adding a separate frontend build system unless NiceGUI itself requires generated assets.

Expected application shape:

- A small app entry point that can run locally for development and inside the existing kind control-plane web app container.
- Server-side adapter functions that continue to produce browser-friendly snapshots, round details, inbox groups, runtime checks, and live update events.
- NiceGUI pages or route handlers for overview, rounds, selected round detail, inbox, runtime, and troubleshooting diagnostics.
- Reusable UI components for status badges, source health rows, live freshness indicators, round summaries, branch evidence, validation summaries, and diagnostic payload containers.

The implementation may reorganize modules and templates freely, but JSON-producing adapter behavior should remain independently testable from NiceGUI widgets.

## Contract Preservation

Existing browser-facing contracts are compatibility boundaries. The NiceGUI migration should preserve:

- health and readiness endpoints used by Kubernetes probes and smoke checks;
- snapshot endpoints used by tests or external scripts;
- round detail and event endpoints used for selected-round inspection;
- live update endpoint semantics, cursor behavior, stale/fallback state, and source-specific errors;
- structured JSON fields for source identifiers, timestamps, statuses, branch fields, validation fields, blockers, warnings, final-review verdicts, and runtime readiness.

NiceGUI may consume these contracts internally, but it should not make automation depend on scraping rendered HTML. If a contract needs to grow, additions should be backward-compatible fields.

## Runtime And Deployment Compatibility

The NiceGUI app should fit the existing deployment model:

- Local execution should work from the repository with the same Python dependency tooling used by the current web app.
- The kind deployment should keep a web app Deployment, Service, labels, probes, read-only ServiceAccount/RBAC, mounted workspace, and Hub dev-auth Secret convention.
- Environment variables such as `SCION_OPS_ROOT`, Hub endpoint values, MCP URL, grove id values, token file paths, and optional GitHub token wiring should keep their existing meanings.
- The service should remain reachable through the documented kind host port path without requiring `kubectl port-forward`.
- Kubernetes readiness and smoke checks should continue to verify the HTTP endpoint and a JSON snapshot or readiness response without starting model-backed work.

NiceGUI startup, static assets, and websocket or polling behavior should be configured so probes and JSON endpoints remain reliable even when live UI clients disconnect or reconnect.

## Operator Information Architecture

The fresh UI should prioritize operational scanning:

- **Overview:** compact readiness summary, live freshness state, active/blocked/recent round counts, and the highest-priority source or round needing attention.
- **Rounds:** dense comparison of active and recent rounds with status, phase, decision flow, validation state, final review, branch evidence, latest update, and blocker summary.
- **Round Detail:** selected-round context with summary first, followed by timeline, agents, decision flow, final review, validation, branches, artifacts, and runner output.
- **Inbox:** operator-relevant messages and notifications grouped by round when possible, with source and timestamp visible.
- **Runtime:** Hub, broker, MCP, Kubernetes, web app deployment, service, pod, PVC, and live update path readiness.
- **Troubleshooting:** one-level-down diagnostic panels exposing raw JSON, source errors, logs, validation payloads, cursor state, and fallback evidence.

The overview should not become a landing page or marketing hero. It should be an operational first screen with compact status, clear severity, and direct drill-ins.

## Laws Of UX Constraints

The interface should explicitly apply Laws of UX principles:

- **Hick's Law:** show the smallest useful set of top-level navigation and actions; keep troubleshooting options grouped below the affected item.
- **Miller's Law:** chunk readiness, rounds, inbox, runtime, and diagnostics into small scannable groups rather than long undifferentiated lists.
- **Fitts's Law:** keep primary navigation, refresh or reconnect controls, and affected-item drill-ins close to their related context and large enough for reliable selection.
- **Jakob's Law:** use familiar operations-console patterns such as status badges, tables, tabs, accordions, detail panes, and timestamped timelines.
- **Law of Proximity and Common Region:** visually group each source error with the source and data it affects, not in a detached global error pile.
- **Tesler's Law:** keep unavoidable complexity in the troubleshooting layer while presenting a concise default state.
- **Doherty Threshold:** keep interactions responsive; show loading, reconnecting, stale, and fallback feedback quickly when source calls are slow.

These constraints should guide layout and interaction decisions, not appear as explanatory text inside the app.

## Visual And Interaction Direction

Use a restrained operations-console style: neutral surfaces, compact spacing, stable dimensions, readable system typography, monospace treatment for code-like values, and semantic accents for state. Color must not be the only status signal; labels, icons, and source-specific text should also communicate state.

Avoid decorative gradients, oversized hero sections, nested cards, ornamental illustrations, broad marketing copy, or one-note color themes. Repeated items may use simple panels or table rows, but page sections should remain efficient and scan-friendly.

Responsive behavior should preserve the primary monitoring workflow on narrow screens. Tables may collapse into row summaries, detail panes may stack, and secondary diagnostic fields may move into expanders, but round identifiers, state, freshness, and blockers should remain visible.

## Read-Only Safety

The NiceGUI app should remain read-only across all visible and background paths. Loading pages, opening diagnostics, live subscriptions, reconnects, fallback polling, health checks, and smoke tests must not mutate Hub runtime records, Kubernetes resources, git refs, OpenSpec files, or round state.

Any future write operations would require a separate OpenSpec change and should not be implied by button placement, placeholder actions, or disabled controls in this migration.

## Verification Strategy

Implementation should include no-spend checks for:

- NiceGUI app startup and route rendering with representative healthy, empty, stale, blocked, degraded, and unavailable data.
- JSON and health endpoint compatibility before and after the frontend replacement.
- Read-only behavior during page load, live update subscription, reconnect, fallback polling, and diagnostic drill-in.
- Kind manifest and lifecycle compatibility, including probes and service reachability.
- Responsive rendering at desktop and narrow widths without blank screens, overlapping controls, or unreadable statuses.
- Laws of UX constraints through focused layout or snapshot checks that prove concise defaults and one-level-down diagnostics.
