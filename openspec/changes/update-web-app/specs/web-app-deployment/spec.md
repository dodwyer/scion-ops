# Delta: Web App Deployment

## ADDED Requirements

### Requirement: Web App Kubernetes Deployment

The scion-ops web app hub SHALL be deployed as a Kubernetes workload in the `scion-agents` namespace using the same image and conventions as the MCP service.

#### Scenario: Web app starts and becomes ready in-cluster

- GIVEN the scion-ops-mcp image is present in the kind cluster
- AND `kubectl apply -k deploy/kind/control-plane` is run
- WHEN the web app Deployment is applied
- THEN a `scion-ops-web` pod reaches Running and Ready state
- AND the readiness probe on HTTP GET `/` at port 8787 succeeds.

#### Scenario: Web app resolves in-cluster MCP service

- GIVEN the `scion-ops-mcp` Service exists in the `scion-agents` namespace
- AND the web app Deployment sets `SCION_OPS_MCP_URL=http://scion-ops-mcp:8765/mcp`
- WHEN the web app renders the Runtime view
- THEN the MCP status shows healthy or a reachable response
- AND no hardcoded IP address is used to reach the MCP service.

#### Scenario: Web app authenticates to the Hub using dev-auth secret

- GIVEN the `scion-hub-dev-auth` secret exists and contains a valid `dev-token`
- AND the web app Deployment mounts the secret at `/run/secrets/scion-hub-dev-auth` and sets `SCION_DEV_TOKEN_FILE`
- WHEN the web app requests Hub API data
- THEN the Hub API responds without auth errors
- AND no token value is hardcoded in the Deployment manifest.

#### Scenario: Web app is included in the kustomize apply

- GIVEN `deploy/kind/control-plane/kustomization.yaml` lists `web-rbac.yaml`, `web-service.yaml`, and `web-deployment.yaml`
- WHEN `kubectl apply -k deploy/kind/control-plane` is run
- THEN the ServiceAccount, Role, RoleBinding, Service, and Deployment for `scion-ops-web` are all applied
- AND no additional manual steps are required.

### Requirement: Web App Kind Port Mapping

The kind cluster template SHALL include a port mapping for the web app so it is reachable from the kind host.

#### Scenario: Kind cluster is created with web app port binding

- GIVEN `deploy/kind/cluster.yaml.tpl` includes a `containerPort: __WEB_NODE_PORT__` / `hostPort: __WEB_HOST_PORT__` mapping
- AND `scripts/kind-scion-runtime.sh` substitutes `WEB_NODE_PORT=30787` and `WEB_HOST_PORT` defaults to 8787
- WHEN `kind create cluster` is called via the bootstrap script
- THEN the kind cluster node exposes port 30787 at the configured host port
- AND the web app is reachable at `http://<kind-host>:<WEB_HOST_PORT>/`.

#### Scenario: Port binding is verified after cluster creation

- GIVEN the kind cluster was created with the web app port mapping
- WHEN the post-create port binding verification runs
- THEN the check includes the web app node port and host port
- AND the status output includes the web app URL alongside the hub and MCP URLs.

## MODIFIED Requirements

### Requirement: Web App Default MCP URL

The web app SHALL resolve the MCP service by in-cluster DNS name when deployed in Kubernetes rather than using a hardcoded development IP.

#### Scenario: In-cluster deployment uses DNS-based MCP URL

- GIVEN the web app Deployment sets `SCION_OPS_MCP_URL=http://scion-ops-mcp:8765/mcp`
- WHEN the web app calls `mcp_status()`
- THEN the request is sent to the MCP service DNS name
- AND the previous hardcoded IP default (`192.168.122.103`) is not used.

#### Scenario: Local development preserves override behaviour

- GIVEN `SCION_OPS_MCP_URL` is set by the operator to a local address
- WHEN the web app is run locally (outside the cluster)
- THEN the operator-supplied value is used unchanged
- AND the Deployment env var does not affect the local run.
