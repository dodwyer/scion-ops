# Goal Clarification: Web App Scion Alignment

## Requested Outcome

Align the existing read-only scion-ops web app hub with the recent MCP service changes made to match Scion runtime behavior, and include the web app in the local `kind`/Kustomize control-plane install path.

Operators should be able to run the normal kind control-plane workflow and get a browser-accessible web app that reports Scion Hub, Runtime Broker, MCP, Kubernetes readiness, rounds, inbox items, notifications, and final review state using the same source-of-truth contracts as the updated MCP service.

## Smallest Useful Change

- Update the web app runtime adapter so it uses the same Scion/MCP configuration conventions as the MCP service, including grove, Hub endpoint/auth, namespace, workspace roots, and in-cluster versus host-facing URLs.
- Add Kubernetes resources for the web app to `deploy/kind/control-plane`, including Deployment, Service, labels, environment, mounts, probes, and RBAC only if the app needs direct Kubernetes API access.
- Add those web app resources to the control-plane Kustomization so `task kind:control-plane:apply` and `task up` install it.
- Ensure the kind install exposes the web app consistently with the existing local control-plane assumptions, preferably without requiring manual port-forwarding.
- Update smoke/status coverage enough to prove the web app is installed and can reach its backing sources in kind.

## Assumptions

- The existing `scripts/web_app_hub.py` read-only app is the web app to align; this is not a request to replace it with a new frontend framework.
- The recent MCP service alignment is the canonical runtime contract for environment variables, Hub auth, Kubernetes namespace discovery, workspace mount paths, and Scion root detection.
- The initial web app remains read-only and must not start, abort, retry, delete, or otherwise mutate rounds.
- The app may share the existing `localhost/scion-ops-mcp:latest` image if that remains the simplest deployable artifact, unless implementation finds a clear need for a separate image.
- The app should be part of the same `scion-control-plane` Kustomize grouping and readiness/status reporting as Hub, broker, and MCP.
- Any documentation updates should be limited to operator-facing usage and status commands needed for the kind-installed web app.

## Non-Goals

- No hosted production deployment, ingress controller, TLS, multi-user auth, or role system.
- No write operations from the web app.
- No change to the core Scion Hub or Runtime Broker behavior unless required to consume their existing APIs correctly.
- No speculative redesign of the web UI beyond changes needed for alignment and installability.

## Unresolved Questions

- Which host port should be reserved for the kind-installed web app, and should it be configurable through the same kind listen-address variables as Hub and MCP?
- Should the web app run in its own Deployment/Service or as an additional container in the MCP Deployment?
- Should Kubernetes status be read through direct in-cluster `kubectl`/API access from the web app pod, or should it rely on existing MCP-normalized status to reduce RBAC surface?
- Is a separate image name desired for the web app, or should the existing MCP image formally become a shared scion-ops tools image?

## Recommended Change Name

`align-web-app-scion-kind`
