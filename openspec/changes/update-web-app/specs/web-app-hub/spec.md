# Delta: Web App Hub

## MODIFIED Requirements

### Requirement: Source Of Truth Preservation

The system SHALL derive displayed operational state from existing scion-ops Hub, MCP, and Kubernetes sources, and SHALL keep browser-visible round semantics aligned with current MCP tool result contracts instead of maintaining separate inference rules.

#### Scenario: App renders MCP-aligned round state

- GIVEN MCP exposes structured round status, event, artifact, final-review, blocker, warning, or validation fields
- WHEN the web app renders rounds, round detail, overview, inbox, or runtime views
- THEN the displayed values are derived from those structured MCP, Hub, or Kubernetes fields
- AND message text, notification text, task summaries, agent names, or slugs are used only as fallback sources when structured fields are unavailable
- AND fallback-derived values are not allowed to override structured MCP or Hub fields.

#### Scenario: Spec round progress is visible

- GIVEN MCP or Hub-backed messages include spec-round progress fields such as expected branch, PR-ready branch, validation status, branch-changed status, protocol milestones, blockers, or warnings
- WHEN an operator opens the rounds or round detail view
- THEN the app shows those fields in operator-readable form
- AND validation failures, missing expected branches, unchanged remote branches, or incomplete protocol milestones are visible as degraded or blocked status rather than generic completion.

#### Scenario: Current final review semantics are preserved

- GIVEN MCP or Hub-backed state includes a final-review verdict, normalized verdict, display label, source summary, or blocking issues
- WHEN the app renders a round row or detail view
- THEN it shows the final-review outcome using the structured verdict fields
- AND changes-requested, revise, failed, or blocked verdicts are displayed as blocked or requiring changes
- AND accepted or approved verdicts are displayed as accepted only when the structured verdict supports that state.

### Requirement: Operator Overview

The system SHALL provide a web overview that summarizes scion-ops readiness from existing Hub, Runtime Broker, MCP, Kubernetes runtime state, and the deployed web app control-plane component.

#### Scenario: Complete kind control plane is ready

- GIVEN Hub is reachable and authenticated
- AND at least one Runtime Broker provider is registered for the active grove
- AND MCP is reachable
- AND required Kubernetes deployments and services for Hub, broker, MCP, and the web app are available
- WHEN an operator opens the overview
- THEN the app shows the control plane as ready
- AND the app shows the contributing Hub, broker, MCP, web app, and Kubernetes checks as healthy.

#### Scenario: Web app deployment is degraded

- GIVEN the web app Deployment, Service, pod, or endpoint is missing or unavailable in the kind control plane
- WHEN an operator opens the overview or runtime view
- THEN the app identifies the web app dependency as degraded or unavailable
- AND it preserves healthy Hub, broker, MCP, and Kubernetes details that are still available.

## ADDED Requirements

### Requirement: MCP Contract Compatibility

The system SHALL keep the web app compatible with current scion-ops MCP tools and SHALL expose their relevant structured state through browser-facing JSON endpoints.

#### Scenario: MCP health and round tools provide structured state

- GIVEN the MCP service exposes `scion_ops_hub_status`, `scion_ops_round_status`, `scion_ops_round_events`, and `scion_ops_watch_round_events`
- WHEN the web app backend refreshes operational state
- THEN it uses these tool result shapes for Hub health, round progress, event timelines, event cursors, terminal status, and final-review outcomes
- AND the browser-facing JSON preserves source identifiers, timestamps, statuses, and error categories needed by the UI.

#### Scenario: MCP artifact and OpenSpec tools provide structured state

- GIVEN the MCP service exposes `scion_ops_round_artifacts`, `scion_ops_spec_status`, and `scion_ops_validate_spec_change`
- WHEN the web app backend has enough context to display branch or OpenSpec details
- THEN it preserves local branch, remote branch, branch SHA, expected branch, PR-ready branch, validation status, and validation errors as explicit JSON fields
- AND the frontend does not parse prose to recover fields that the MCP result already provided.

#### Scenario: MCP service is unreachable

- GIVEN the web app can reach Hub or Kubernetes but cannot reach MCP
- WHEN the backend refreshes operational state
- THEN MCP-specific data is marked with a source-specific error category
- AND the app continues rendering available Hub and Kubernetes data instead of blanking the full interface.

### Requirement: Kind Kustomize Installation

The system SHALL include the web app in the local kind control-plane kustomize install.

#### Scenario: Control-plane kustomization is rendered

- GIVEN an operator runs the control-plane kustomize apply path
- WHEN kustomize renders `deploy/kind/control-plane`
- THEN the rendered resources include a web app Deployment
- AND include a web app Service
- AND include any read-only ServiceAccount, RBAC, ConfigMap, Secret mount, workspace mount, and environment configuration required for the web app to inspect Hub, MCP, and Kubernetes readiness.

#### Scenario: Web app uses in-cluster Scion configuration

- GIVEN the web app runs inside the kind control plane
- WHEN it loads runtime configuration
- THEN it uses the in-cluster Hub endpoint
- AND it uses the in-cluster MCP service URL and path
- AND it uses the active grove id from the mounted scion-ops checkout when available
- AND it reads Hub dev auth from the same mounted Secret convention used by MCP.

#### Scenario: Web app is reachable without port-forwarding

- GIVEN the kind control plane has been created with the configured host port mappings
- WHEN the web app Service is ready
- THEN an operator can open the configured web app URL from the host without running `kubectl port-forward`
- AND the URL and port are documented alongside the Hub and MCP defaults.

### Requirement: Kind Lifecycle Tasks

The system SHALL include the web app in kind lifecycle and verification commands that represent a complete local control-plane install.

#### Scenario: Operator brings up the control plane

- GIVEN an operator runs the standard kind bring-up or update workflow
- WHEN `task up` reconciles the control plane
- THEN the web app image is built or loaded when required
- AND the web app kustomize resources are applied
- AND rollout status includes the web app Deployment.

#### Scenario: Operator updates only the web app

- GIVEN an operator is iterating on the web app
- WHEN they run the narrow web app update workflow
- THEN the workflow rebuilds or reloads only the required web app image when applicable
- AND restarts the web app Deployment
- AND reports web app rollout status and service information.

#### Scenario: No-spend smoke includes the web app endpoint

- GIVEN the kind control plane is deployed
- WHEN the no-spend control-plane smoke check runs
- THEN it verifies the web app HTTP endpoint responds
- AND it verifies the app can render a readiness or snapshot response
- AND it does not start model-backed rounds or mutate Hub runtime state.
