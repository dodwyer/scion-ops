# Delta: Web App Deployment

## ADDED Requirements

### Requirement: Web App Container Image

The system SHALL build a dedicated container image for the scion-ops web dashboard that packages `scripts/web_app_hub.py` and its runtime dependencies independently of the scion-ops-mcp image.

#### Scenario: Image is built successfully

- GIVEN the repository contains `image-build/scion-ops-web/Dockerfile`
- WHEN `task build:web` is executed
- THEN the image `localhost/scion-ops-web:latest` is produced
- AND the image contains a Python environment with `mcp>=1.13,<2` and `PyYAML>=6,<7`
- AND the image exposes port 8787.

#### Scenario: Image is loaded into kind cluster

- GIVEN `localhost/scion-ops-web:latest` has been built
- WHEN `task kind:load-images` is executed
- THEN the image is available to the kind cluster nodes
- AND it is loaded alongside the existing scion-base, scion-ops-mcp, and task-runtime images.

### Requirement: Kind Cluster Port Mapping

The kind cluster template SHALL expose the web app service on the host network without requiring kubectl port-forward.

#### Scenario: Cluster is created with web port mapping

- GIVEN `deploy/kind/cluster.yaml.tpl` includes an `extraPortMappings` entry for the web NodePort
- AND `scripts/kind-scion-runtime.sh` substitutes `__WEB_NODE_PORT__` and `__WEB_HOST_PORT__` with their configured values
- WHEN a new kind cluster is created
- THEN the cluster maps NodePort 30787 to host port 18787 on the configured `KIND_LISTEN_ADDRESS`
- AND the mapping is visible in the rendered cluster configuration.

#### Scenario: Web dashboard is reachable from host after task up

- GIVEN the kind cluster is running with the web port mapping
- AND the web app pod has reached Running state
- WHEN an operator sends an HTTP GET to `http://<KIND_LISTEN_ADDRESS>:18787/`
- THEN the response status is 200
- AND no kubectl port-forward process is required.

### Requirement: Web App Kubernetes Deployment

The system SHALL run the web app hub as a Kubernetes Deployment in the `scion-agents` namespace, following the same structural patterns as scion-ops-mcp.

#### Scenario: Web app pod starts and becomes ready

- GIVEN the web app Deployment manifest references `localhost/scion-ops-web:latest`
- AND the Deployment sets `SCION_OPS_WEB_HOST=0.0.0.0`, `SCION_OPS_WEB_PORT=8787`, and `SCION_OPS_HUB_ENDPOINT=http://scion-hub:8090`
- AND the Deployment mounts the `/workspace` host path and the checkouts PVC
- WHEN `task up` applies the manifests and waits for rollout
- THEN the web app pod reaches Running state
- AND the HTTP readiness probe on port 8787 passes
- AND the Deployment rollout is reported as complete.

#### Scenario: Web app uses dedicated service account

- GIVEN the web app Deployment references ServiceAccount `scion-ops-web`
- WHEN the pod is scheduled
- THEN it runs under the `scion-ops-web` ServiceAccount
- AND it does not share identity credentials with the scion-ops-mcp ServiceAccount.

#### Scenario: Web app has read-only Kubernetes RBAC

- GIVEN `deploy/kind/control-plane/web-rbac.yaml` defines `ServiceAccount/scion-ops-web`, `Role/scion-ops-web`, and `RoleBinding/scion-ops-web`
- AND the Role grants `get`, `list`, and `watch` on `deployments` in the `apps` API group
- AND the Role grants `get`, `list`, and `watch` on core `pods`, `services`, and `persistentvolumeclaims`
- WHEN the web app pod runs under `ServiceAccount/scion-ops-web`
- THEN it can read deployment, pod, service, and PVC state in the `scion-agents` namespace
- AND it is not granted create, update, patch, or delete permissions by the web app Role.

#### Scenario: Web app RoleBinding binds only the web ServiceAccount

- GIVEN `RoleBinding/scion-ops-web` exists in the `scion-agents` namespace
- WHEN the RoleBinding is inspected
- THEN its subject is `ServiceAccount/scion-ops-web`
- AND its roleRef points to `Role/scion-ops-web`
- AND it does not bind the scion-ops-mcp ServiceAccount.

#### Scenario: Web app receives Hub auth token

- GIVEN the `scion-hub-dev-auth` Secret exists in the `scion-agents` namespace
- AND the web app Deployment mounts the Secret read-only at `/run/secrets/scion-hub-dev-auth`
- AND the web app Deployment sets `SCION_DEV_TOKEN_FILE=/run/secrets/scion-hub-dev-auth/dev-token`
- WHEN the web app pod starts
- THEN the Hub auth token is available to the process via the token file
- AND the Deployment does not inject `SCION_DEV_TOKEN` via `secretKeyRef`
- AND the web app can authenticate against the Hub API.

### Requirement: Web App NodePort Service

The system SHALL expose the web app on a NodePort Service so the kind cluster port mapping can forward traffic to the pod.

#### Scenario: Service routes to web app pod

- GIVEN `deploy/kind/control-plane/web-service.yaml` defines a NodePort Service with nodePort 30787 targeting containerPort 8787
- WHEN the Service and Deployment are applied
- THEN cluster-internal traffic to the Service reaches the web app pod on port 8787
- AND host traffic arriving on port 18787 is forwarded through NodePort 30787 to the pod.

### Requirement: Kustomization Includes Web Resources

The system SHALL include all web app manifests in the kind control-plane Kustomization so they are applied and managed as a unit with the other control-plane services.

#### Scenario: Web resources are applied with task up

- GIVEN `deploy/kind/control-plane/kustomization.yaml` lists `web-rbac.yaml`, `web-deployment.yaml`, and `web-service.yaml`
- WHEN `task up` runs `kubectl apply -k deploy/kind/control-plane`
- THEN all three web resources are created or updated in the cluster
- AND no separate apply step is required for the web app.

### Requirement: Smoke Test Covers Web Endpoint

The system SHALL verify that the web dashboard endpoint is reachable as part of the standard `task test` smoke check.

#### Scenario: Smoke check passes for healthy web app

- GIVEN the web app pod is Running and the NodePort Service is active
- WHEN the smoke check script sends an HTTP GET to `http://<KIND_LISTEN_ADDRESS>:<WEB_HOST_PORT>/`
- THEN it receives HTTP 200
- AND the smoke check reports the web endpoint as healthy.

#### Scenario: Smoke check fails for unreachable web app

- GIVEN the web app pod is not Running or the Service is not reachable
- WHEN the smoke check script sends an HTTP GET to the web endpoint
- THEN it receives a non-200 response or a connection error
- AND the smoke check reports a failure specific to the web endpoint
- AND existing hub and mcp smoke checks are reported independently.

### Requirement: Existing Control Plane Services Unaffected

The system SHALL add the web app to the kind deployment without disrupting scion-hub, scion-broker, or scion-ops-mcp.

#### Scenario: task up succeeds with all four services

- GIVEN the web app manifests and port mapping have been added
- WHEN `task up` completes
- THEN scion-hub, scion-broker, scion-ops-mcp, and scion-ops-web pods all reach Running state
- AND the hub NodePort 30090, mcp NodePort 30876, and web NodePort 30787 are each individually reachable.
