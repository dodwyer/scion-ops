# Clarifier Findings: update-web-app

## Recommended Change Name

`align-web-app-with-scion-mcp-and-kind`

## Goal Clarification

Update the existing read-only scion-ops web app so it remains compatible with the recent MCP service alignment to Scion, and make the web app part of the local kind/kustomize control-plane install.

The implementation change should cover two related surfaces:

1. Web app runtime alignment
   - Ensure the web app uses the same MCP transport, URL/path, host, port, Hub endpoint, auth token, grove, namespace, and source-of-truth assumptions now used by `mcp_servers/scion_ops.py`.
   - Preserve the current read-only behavior: the app may inspect Hub, MCP, and Kubernetes state, but must not start, abort, retry, delete, or mutate rounds.
   - Keep displayed state derived from Scion Hub, MCP, Kubernetes, or existing normalized scion-ops helpers, rather than introducing an independent persistent state store.

2. kind/kustomize installation
   - Add first-class Kubernetes manifests for the web app under the kind control-plane overlay.
   - Include those manifests in the relevant `kustomization.yaml` so `task up` / kind apply installs the web app with Hub, broker, and MCP.
   - Expose the app in a way consistent with the existing local kind networking model, likely as a Service and, if needed, a kind host-port/NodePort mapping.
   - Ensure deployment labels, resource ownership labels, namespace, service account/RBAC needs, config/env, probes, and image/runtime command follow the existing control-plane conventions.

## Current Context Observed

- `scripts/web_app_hub.py` is the existing read-only browser hub. It imports `mcp_servers.scion_ops`, defaults `SCION_OPS_MCP_URL` to `http://192.168.122.103:8765/mcp`, and normalizes Hub, MCP, Kubernetes, round, inbox, and final-review state for display.
- `mcp_servers/scion_ops.py` now centralizes MCP server settings through `SCION_OPS_MCP_HOST`, `SCION_OPS_MCP_PORT`, `SCION_OPS_MCP_PATH`, `SCION_OPS_MCP_JSON_RESPONSE`, and `SCION_OPS_MCP_STATELESS_HTTP`, with streamable HTTP as the deployed transport.
- `deploy/kind/control-plane/kustomization.yaml` currently includes Hub, broker, and MCP resources, but no dedicated web app deployment or service.
- `deploy/kind/control-plane/hub-deployment.yaml` enables Scion's built-in web surface on the Hub container at port `8090`; that is separate from the scion-ops read-only web app script unless the implementer intentionally decides to consolidate them.
- `Taskfile.yml` has a local `web:hub` task that runs `uv run scripts/web_app_hub.py`, but the kind control-plane tasks and status selectors currently focus on Hub, broker, and MCP.

## Assumptions

- The requested "web app" means the scion-ops read-only browser app implemented in `scripts/web_app_hub.py`, not Scion Hub's built-in `--enable-web` UI.
- The MCP service alignment already landed or is expected to land separately; this change should adapt the web app to that contract, not redesign the MCP service itself.
- The kind install should deploy the web app as a long-running Kubernetes workload alongside `scion-hub`, `scion-broker`, and `scion-ops-mcp`.
- The web app can use the same `localhost/scion-ops-mcp:latest` or another existing image only if that image contains the web app script and its dependencies; otherwise the implementation should add the minimal image/build plumbing needed.
- The web app may need Kubernetes read permissions if it continues to show Kubernetes deployment readiness from inside the cluster.
- The web app should be reachable by local operators after `task up` without manual `kubectl port-forward`.

## Unresolved Questions

- Should the web app run from the MCP image, from the base Scion image, or from a new purpose-built image?
- What external port should kind expose for the web app, and should it be a NodePort plus kind host-port mapping like Hub/MCP?
- Should the web app call the MCP server over in-cluster service DNS (`http://scion-ops-mcp:8765/mcp`) when deployed, while keeping the current host URL default for local script use?
- Should operator authentication for the web app be added now, or is it acceptable for the initial kind deployment to match the current read-only/no-auth local script?
- Should Taskfile status/smoke commands be extended to include the web app deployment, service, and HTTP readiness endpoint?
- Should the OpenSpec delta update the existing `build-web-app-hub` change, or should this be a new follow-up OpenSpec change named `align-web-app-with-scion-mcp-and-kind`?

## Suggested Acceptance Criteria

- Running the web app locally still works through `task web:hub`.
- Running the web app in kind uses in-cluster Hub and MCP endpoints by default.
- `kustomize build deploy/kind/control-plane` includes the web app workload and service.
- `task up` installs the web app as part of the control plane.
- The deployed app reports Hub, broker, MCP, and Kubernetes readiness without relying on stale host-only defaults.
- Existing web app tests continue to pass, with new tests or smoke coverage for deployed configuration where practical.
