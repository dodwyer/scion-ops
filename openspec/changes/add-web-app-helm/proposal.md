# Proposal: Add Web App Hub to Kind Deployment

## Summary

Deploy the already-merged scion-ops web dashboard (`scripts/web_app_hub.py`) as a 4th control-plane service in the kind cluster, alongside scion-hub, scion-broker, and scion-ops-mcp. After `task up`, the web dashboard will be reachable at `http://<KIND_LISTEN_ADDRESS>:18787/` without port-forwarding.

Despite the change name, this change intentionally uses the existing kind control-plane Kustomize flow rather than introducing Helm. This is an accepted minimal-templating exception: the current kind control-plane deployment already uses Kustomize, and adding a Helm chart only for the web app would either create a mixed packaging model or require converting the three existing services in the same change. That conversion is outside this change's scope.

## Motivation

`scripts/web_app_hub.py` ships in the merged codebase and is runnable locally via `task web:hub`. However, it is not yet part of the kind deployment, so operators who start the cluster with `task up` cannot access the dashboard without a separate local process. Closing this gap makes the web dashboard a first-class control-plane service, consistent with how scion-hub and scion-ops-mcp are served.

## Scope

In scope:

- A dedicated container image (`localhost/scion-ops-web:latest`) built from a new `image-build/scion-ops-web/Dockerfile`.
- Kubernetes manifests for the web app: ServiceAccount, read-only Role, RoleBinding, Deployment, and NodePort Service in the `scion-agents` namespace.
- Kind cluster port mapping: NodePort 30787 → host port 18787 on `__KIND_LISTEN_ADDRESS__`.
- Kustomization update to include the new web resources.
- Taskfile updates: `build:web` task, `kind:load-images` inclusion, `SCION_OPS_KIND_WEB_PORT` variable.
- Smoke-test extension to verify the web endpoint returns HTTP 200 after `task up`.

Out of scope:

- Changes to `scripts/web_app_hub.py` or its runtime behavior.
- Write operations or mutating endpoints in the web app.
- TLS, authentication, or multi-user access controls.
- Replacing or modifying the scion-ops-mcp image.

## Success Criteria

- `task up` completes and the web app pod reaches the Running state.
- `http://<KIND_LISTEN_ADDRESS>:18787/` is reachable from the host without port-forwarding and returns a non-error response.
- `task test` smoke check includes a verification step for the web endpoint.
- No existing control-plane service (hub, broker, mcp) is disrupted by the change.

## Unresolved Questions

All open questions from the clarifier have recommended decisions captured in `design.md`. No blockers remain.
