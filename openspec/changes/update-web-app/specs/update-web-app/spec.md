# Delta: Update Web App

## MODIFIED Requirements

### Requirement: MCP Port Environment Variable Handling

The system SHALL resolve `SCION_OPS_MCP_PORT` using the `_env_port` helper
present in `mcp_servers/scion_ops.py` rather than applying a pre-import
workaround in `scripts/web_app_hub.py`.

#### Scenario: Port env var is a plain integer string

- GIVEN `SCION_OPS_MCP_PORT` is set to a plain integer string such as `"8765"`
- WHEN `web_app_hub.py` imports `mcp_servers.scion_ops`
- THEN the import succeeds without clearing or modifying the env var
- AND the MCP module binds to the specified port.

#### Scenario: Port env var is a URL string

- GIVEN `SCION_OPS_MCP_PORT` is set to a URL string such as `"http://host:8765"`
- WHEN `web_app_hub.py` imports `mcp_servers.scion_ops`
- THEN the import succeeds without the env var being cleared
- AND `_env_port` in `scion_ops.py` extracts the port from the URL.

#### Scenario: Port env var is absent

- GIVEN `SCION_OPS_MCP_PORT` is not set
- WHEN `web_app_hub.py` imports `mcp_servers.scion_ops`
- THEN the MCP module uses its default port of `8765`.

### Requirement: Round Detail Final Failure Fields

The system SHALL display `final_failure_classification` and
`final_failure_evidence` in the round detail view when those fields are
non-empty in the outcome data returned by `_final_review_outcome`.

#### Scenario: Final failure classification is present

- GIVEN a completed round has a `final_failure_classification` value in its
  outcome
- WHEN an operator opens the round detail view
- THEN the classification is shown in the final review section alongside
  existing fields such as `blocking_issues`.

#### Scenario: Final failure evidence is present

- GIVEN a completed round has a `final_failure_evidence` value in its outcome
- WHEN an operator opens the round detail view
- THEN the evidence is shown in the final review section.

#### Scenario: Final failure fields are absent

- GIVEN a completed round has no `final_failure_classification` or
  `final_failure_evidence` in its outcome
- WHEN an operator opens the round detail view
- THEN the final review section renders without those fields and no empty
  placeholders are shown.

### Requirement: Control Plane Readiness Includes Web App

The system SHALL include the `scion-ops-web` deployment in the set of
control-plane components tracked for runtime readiness.

#### Scenario: Web app deployment is ready

- GIVEN the `scion-ops-web` Kubernetes deployment is available and all pods
  are ready
- WHEN an operator views the runtime readiness overview
- THEN `scion-ops-web` appears as a healthy component.

#### Scenario: Web app deployment is not ready

- GIVEN the `scion-ops-web` Kubernetes deployment is missing or has no ready
  pods
- WHEN an operator views the runtime readiness overview
- THEN the control plane is shown as degraded
- AND `scion-ops-web` is identified as the failing component.

## ADDED Requirements

### Requirement: Web App Kubernetes Deployment

The system SHALL provide a Kubernetes Deployment for the scion-ops web app hub
in the kind control-plane kustomize overlay, reusing the `scion-ops-mcp` image
and workspace hostPath mount.

#### Scenario: Control-plane apply includes web app

- GIVEN the kind control-plane kustomize overlay is applied
- WHEN the apply completes
- THEN a `scion-ops-web` Deployment exists in the `scion-agents` namespace
- AND the deployment runs `scripts/web_app_hub.py` with `SCION_OPS_WEB_HOST=0.0.0.0`
- AND the deployment mounts the workspace hostPath volume.

#### Scenario: Web app pod reaches ready state

- GIVEN the `scion-ops-web` Deployment has been applied
- WHEN the pod starts
- THEN the readiness probe succeeds on port `8787`
- AND the pod is marked ready.

### Requirement: Web App NodePort Service

The system SHALL provide a NodePort Service for the scion-ops web app that
exposes port `8787` as nodePort `30787`.

#### Scenario: Web app is reachable via node port

- GIVEN the kind cluster is running and the web app pod is ready
- WHEN an operator sends an HTTP request to the kind node on port `30787`
- THEN the web app responds with its HTML interface.

### Requirement: Web App Host Port Mapping in Kind Cluster

The system SHALL include a host port mapping for the web app in the kind
cluster configuration template so operators can reach the web app at a
configured host address and port.

#### Scenario: Kind cluster is created with web port mapping

- GIVEN `SCION_OPS_KIND_WEB_PORT` is set (default `8787`)
- WHEN the kind cluster is created using the cluster template
- THEN the kind node exposes `nodePort 30787` on the configured host address
  and port.

#### Scenario: Operator reaches web app at host port

- GIVEN the kind cluster is running with the web port mapping
- WHEN an operator opens `http://<KIND_LISTEN_ADDRESS>:<SCION_OPS_KIND_WEB_PORT>/`
- THEN the scion-ops web app hub interface is served.

### Requirement: Web App Port Variable Propagation

The system SHALL propagate the web app host port through `Taskfile.yml` and
`scripts/kind-scion-runtime.sh` following the same pattern as the existing hub
and MCP port variables.

#### Scenario: Default web port is used when variable is unset

- GIVEN `SCION_OPS_KIND_WEB_PORT` is not set in the environment
- WHEN `scripts/kind-scion-runtime.sh` creates the kind cluster
- THEN the web app host port defaults to `8787`.

#### Scenario: Custom web port is used when variable is set

- GIVEN `SCION_OPS_KIND_WEB_PORT` is set to a custom port
- WHEN `scripts/kind-scion-runtime.sh` creates the kind cluster
- THEN the kind node maps nodePort `30787` to the custom host port.
