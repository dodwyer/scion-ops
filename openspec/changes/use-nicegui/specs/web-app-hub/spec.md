# Delta: Web App Hub

## MODIFIED Requirements

### Requirement: Operator Overview

The system SHALL provide a NiceGUI operator overview that summarizes scion-ops readiness from existing Hub, Runtime Broker, MCP, Kubernetes runtime state, the deployed web app control-plane component, and live update freshness.

#### Scenario: Operator opens the NiceGUI overview

- GIVEN Hub is reachable and authenticated
- AND at least one Runtime Broker provider is registered for the active grove
- AND MCP is reachable
- AND required Kubernetes deployments and services for Hub, broker, MCP, and the web app are available
- AND the live update path is fresh or connected
- WHEN an operator opens the NiceGUI overview
- THEN the app shows the control plane as ready
- AND shows contributing Hub, broker, MCP, web app, Kubernetes, and live update checks as healthy
- AND shows active, blocked, and recent round context without requiring the operator to open a diagnostic view.

#### Scenario: Overview prioritizes concise operator context

- GIVEN one or more rounds, sources, or live update paths are blocked, failed, stale, degraded, or unavailable
- WHEN an operator opens the NiceGUI overview
- THEN the app identifies the highest-priority affected source or round
- AND shows concise status, last update time, and next inspection target
- AND keeps raw payloads, long logs, and low-level troubleshooting details out of the default overview.

#### Scenario: Overview exposes troubleshooting one level down

- GIVEN overview data includes source errors, validation failures, branch mismatches, stale cursor state, or runner diagnostics
- WHEN an operator drills into the affected check, round, or diagnostic control
- THEN the NiceGUI app shows the relevant detailed troubleshooting information one interaction level below the overview
- AND preserves healthy source details that are still available.

### Requirement: Source Of Truth Preservation

The system SHALL derive NiceGUI-displayed operational state from existing scion-ops Hub, MCP, Kubernetes, and normalized helper sources, while keeping browser-visible JSON contracts aligned with current MCP and web app tool result contracts.

#### Scenario: NiceGUI renders source-backed state

- GIVEN MCP, Hub, Kubernetes, or normalized helper output exposes structured readiness, round, event, artifact, validation, final-review, blocker, warning, or branch fields
- WHEN the NiceGUI app renders overview, rounds, round detail, inbox, runtime, or troubleshooting views
- THEN the displayed values are derived from those structured source fields
- AND message text, notification text, task summaries, agent names, or slugs are used only as fallback sources when structured fields are unavailable
- AND fallback-derived values are not allowed to override structured MCP or Hub fields.

#### Scenario: Browser JSON contract remains compatible

- GIVEN existing tests, smoke checks, or external scripts request browser-facing JSON snapshot, round detail, round event, live update, or health endpoints
- WHEN the web app frontend has been replaced with NiceGUI
- THEN those endpoints remain available with backward-compatible field names and semantics
- AND source identifiers, timestamps, statuses, branch fields, validation fields, blockers, warnings, final-review verdicts, cursor values, live update state, and source-specific errors remain explicit JSON fields
- AND automation does not need to scrape NiceGUI-rendered HTML to recover operational state.

#### Scenario: Backing source fails under NiceGUI

- GIVEN one backing source is unavailable
- WHEN the NiceGUI app renders or updates a view that also depends on other sources
- THEN it shows a source-specific error for the unavailable dependency
- AND continues showing data from sources that responded successfully
- AND does not clear previously visible data unless the source-of-truth response explicitly indicates the data is gone.

### Requirement: Read Only Initial Interface

The system SHALL keep the NiceGUI web app read-only and SHALL NOT expose round-starting, aborting, retrying, deleting, archiving, git-writing, OpenSpec-writing, or Kubernetes-mutating operations.

#### Scenario: Operator uses NiceGUI views

- GIVEN an operator opens overview, rounds, round detail, inbox, runtime, or troubleshooting views
- WHEN the app loads, refreshes data, expands diagnostics, follows drill-ins, or receives live updates
- THEN it does not start rounds
- AND it does not abort, retry, delete, archive, or mutate rounds
- AND it does not modify Kubernetes resources, Hub runtime records, git refs, or OpenSpec files.

#### Scenario: Automatic update recovery remains read-only

- GIVEN the NiceGUI app subscribes, reconnects, resumes from a cursor, or falls back to polling
- WHEN the automatic update path recovers from stale or disconnected state
- THEN recovery performs only read operations against Hub, MCP, Kubernetes, git, and OpenSpec status sources
- AND no state-changing operation is exposed as an implied or hidden side effect.

### Requirement: Kind Kustomize Installation

The system SHALL run the NiceGUI web app in the local kind control-plane install while preserving the existing web app Deployment, Service, probe, workspace, auth, and read-only runtime conventions.

#### Scenario: Control-plane kustomization is rendered for NiceGUI

- GIVEN an operator runs the control-plane kustomize apply path
- WHEN kustomize renders `deploy/kind/control-plane`
- THEN the rendered resources include a web app Deployment that starts the NiceGUI application
- AND include a web app Service with the existing stable service identity and port compatibility
- AND include any read-only ServiceAccount, RBAC, ConfigMap, Secret mount, workspace mount, probes, and environment configuration required for NiceGUI to inspect Hub, MCP, and Kubernetes readiness.

#### Scenario: NiceGUI uses in-cluster Scion configuration

- GIVEN the NiceGUI app runs inside the kind control plane
- WHEN it loads runtime configuration
- THEN it uses the in-cluster Hub endpoint
- AND it uses the in-cluster MCP service URL and path
- AND it uses the active grove id from the mounted scion-ops checkout when available
- AND it reads Hub dev auth from the same mounted Secret convention used by MCP and the previous web app.

#### Scenario: NiceGUI remains reachable through existing local workflow

- GIVEN the kind control plane has been created with the configured host port mappings
- WHEN the NiceGUI web app Service is ready
- THEN an operator can open the configured web app URL from the host without running `kubectl port-forward`
- AND existing smoke checks can reach health or JSON snapshot endpoints without starting model-backed rounds.

## ADDED Requirements

### Requirement: NiceGUI Frontend

The system SHALL replace the web UI frontend with a NiceGUI application that starts from a fresh operator-console interface while preserving the existing server-side source contracts.

#### Scenario: NiceGUI application starts

- GIVEN the web app process is started locally or inside the kind deployment
- WHEN the HTTP server becomes ready
- THEN it serves a NiceGUI-rendered operator interface
- AND exposes health, snapshot, round detail, round events, and live update endpoints required by existing tests and smoke checks
- AND does not require a separate JavaScript single-page application build pipeline.

#### Scenario: Fresh interface structure is used

- GIVEN the prior web UI page structure exists as historical context
- WHEN the NiceGUI frontend is implemented
- THEN the visible interface is organized around operator overview, rounds, round detail, inbox, runtime, and troubleshooting tasks
- AND implementation is not required to preserve prior HTML structure, CSS classes, or page layout
- AND externally consumed JSON and health contracts remain compatible.

#### Scenario: NiceGUI components preserve operator state during updates

- GIVEN an operator has selected a round, expanded a diagnostic section, or is viewing a filtered list
- WHEN live update, reconnect, or fallback polling data arrives
- THEN NiceGUI updates affected status, timeline, inbox, runtime, and freshness components without forcing a full page reload
- AND preserves selected context where the backing source still supports it
- AND avoids duplicate visible timeline or inbox entries for replayed update events.

### Requirement: Progressive Troubleshooting

The system SHALL present concise action- and context-related information by default, with in-depth troubleshooting information available one level down.

#### Scenario: Default screens stay concise

- GIVEN an operator opens overview, rounds, inbox, or runtime
- WHEN the screen renders
- THEN it shows operational state, severity, affected source or round, timestamp, and short blocker or outcome summaries first
- AND avoids showing raw JSON, long logs, full validation output, or exhaustive source payloads by default
- AND provides an obvious drill-in to the relevant details when deeper inspection is available.

#### Scenario: Detailed diagnostics are one level down

- GIVEN detailed diagnostics exist for a source, round, validation result, branch check, runner output, live cursor, or fallback state
- WHEN the operator opens the related detail pane, tab, expander, drawer, or troubleshooting view
- THEN the app shows the in-depth diagnostic information next to the context it explains
- AND preserves timestamps, source labels, error categories, structured fields, and raw payloads when available.

#### Scenario: Default view points to the next useful inspection

- GIVEN a source or round is blocked, failed, stale, degraded, unavailable, or changes-requested
- WHEN the operator views its concise summary
- THEN the app identifies the likely next inspection target, such as runtime source, final review, validation, branch evidence, timeline, or runner output
- AND the drill-in opens that context without requiring the operator to search through unrelated diagnostics.

### Requirement: Laws Of UX Design Constraints

The system SHALL apply Laws of UX principles to the NiceGUI frontend so repeated operational monitoring remains fast, understandable, and low-friction.

#### Scenario: Information is chunked and grouped

- GIVEN overview, rounds, round detail, inbox, runtime, or troubleshooting views contain multiple sources of operational state
- WHEN the NiceGUI app renders them
- THEN related state is grouped by source, round, timeline, validation, branch, or runtime dependency
- AND the app avoids long undifferentiated lists of mixed status, log, and payload data
- AND the layout supports recognition of state rather than requiring recall of hidden meanings.

#### Scenario: Choices and actions are kept close to context

- GIVEN an operator can navigate, refresh, reconnect, filter, expand, or drill into a status item
- WHEN those controls are rendered
- THEN the available choices are limited to the relevant context
- AND controls are placed near the state they affect
- AND interaction targets are large and stable enough for reliable selection on desktop and narrow screens.

#### Scenario: Feedback is timely and explicit

- GIVEN a source call, live update subscription, reconnect, fallback poll, or diagnostic load is in progress or delayed
- WHEN the NiceGUI app waits for fresh data
- THEN it shows loading, connected, reconnecting, stale, fallback, or failed feedback promptly
- AND does not imply that an underlying round, source, validation, or final review succeeded merely because the UI request completed.

### Requirement: NiceGUI Responsive Operator Layout

The system SHALL keep the NiceGUI frontend usable and readable at typical desktop and narrow mobile widths.

#### Scenario: Desktop viewport supports dense scanning

- GIVEN the browser viewport is desktop width
- WHEN an operator opens overview, rounds, round detail, inbox, runtime, or troubleshooting views
- THEN the app uses available width for efficient scanning
- AND status, timestamps, branch evidence, validation state, final-review outcome, blockers, and live freshness remain visible without excessive whitespace or decorative framing.

#### Scenario: Narrow viewport preserves primary workflow

- GIVEN the browser viewport is narrow
- WHEN an operator opens overview, rounds, round detail, inbox, runtime, or troubleshooting views
- THEN navigation, status labels, tables or row summaries, metadata, diagnostic controls, and action buttons do not overlap
- AND essential round identifiers, source names, state, freshness, and blocker summaries remain visible
- AND secondary columns or raw diagnostic details may wrap, collapse, or move behind one-level-down controls.

#### Scenario: Keyboard and accessibility basics are preserved

- GIVEN an operator navigates the NiceGUI app with a keyboard or assistive technology
- WHEN focus moves through navigation, refresh, reconnect, filters, expanders, tabs, detail controls, and clickable round rows
- THEN focused elements have visible focus treatment
- AND statuses are communicated by labels, icons, or text in addition to color
- AND text and semantic accents have sufficient contrast for an internal operations console.
