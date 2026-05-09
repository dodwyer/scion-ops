# Tasks

- [ ] 1.1 Create `image-build/scion-ops-web/Dockerfile` based on `localhost/scion-base:latest`, installing `mcp>=1.13,<2` and `PyYAML>=6,<7`, exposing port 8787, with entrypoint `python /workspace/scion-ops/scripts/web_app_hub.py`.
- [ ] 1.2 Add `deploy/kind/control-plane/web-rbac.yaml` with a `ServiceAccount` named `scion-ops-web` in namespace `scion-agents`.
- [ ] 1.3 In `web-rbac.yaml`, add a namespaced `Role` named `scion-ops-web` granting `get`, `list`, and `watch` on `deployments` in API group `apps` and on core `pods`, `services`, and `persistentvolumeclaims`.
- [ ] 1.4 In `web-rbac.yaml`, add a `RoleBinding` named `scion-ops-web` binding `Role/scion-ops-web` to `ServiceAccount/scion-ops-web`.
- [ ] 1.5 Add `deploy/kind/control-plane/web-deployment.yaml`: Deployment using `localhost/scion-ops-web:latest`, env vars `SCION_OPS_WEB_HOST=0.0.0.0`, `SCION_OPS_WEB_PORT=8787`, `SCION_OPS_HUB_ENDPOINT=http://scion-hub:8090`, `SCION_HUB_ENDPOINT=http://scion-hub:8090`, and `SCION_DEV_TOKEN_FILE=/run/secrets/scion-hub-dev-auth/dev-token`; mount the `scion-hub-dev-auth` Secret read-only at `/run/secrets/scion-hub-dev-auth`; mount `/workspace` and checkouts PVCs matching the mcp pattern; add HTTP readiness/liveness probes on port 8787.
- [ ] 1.6 Add `deploy/kind/control-plane/web-service.yaml`: NodePort Service mapping port 8787 to NodePort 30787.
- [ ] 1.7 Update `deploy/kind/control-plane/kustomization.yaml` to include `web-rbac.yaml`, `web-deployment.yaml`, and `web-service.yaml` in the resources list.
- [ ] 1.8 Update `deploy/kind/cluster.yaml.tpl` to add an `extraPortMappings` entry for `__WEB_NODE_PORT__` → `__WEB_HOST_PORT__` on `__KIND_LISTEN_ADDRESS__`.
- [ ] 1.9 Update `scripts/kind-scion-runtime.sh` to substitute `__WEB_NODE_PORT__` and `__WEB_HOST_PORT__` template variables when rendering `cluster.yaml.tpl`, sourcing values from Taskfile or environment defaults (30787 / 18787).
- [ ] 1.10 Extend `scripts/build-images.sh` with web image support, including targeted `--only web`, building `localhost/scion-ops-web:latest` from `image-build/scion-ops-web/`.
- [ ] 1.11 Add `build:web` task to `Taskfile.yml` that invokes `scripts/build-images.sh --only web` rather than bypassing the shared build script.
- [ ] 1.12 Add `SCION_OPS_KIND_WEB_PORT: 18787` variable to `Taskfile.yml` and update `kind:load-images` to include `localhost/scion-ops-web:latest`.
- [ ] 1.13 Keep `WEB_HOST_PORT`, `WEB_NODE_PORT`, and container port values defined through Taskfile/runtime variables so the rendered cluster mapping, service, deployment, and smoke check share one source of truth.
- [ ] 1.14 Extend `scripts/kind-control-plane-smoke.py` (or equivalent smoke check) to send an HTTP GET to `http://<KIND_LISTEN_ADDRESS>:<WEB_HOST_PORT>/` and assert HTTP 200.
- [ ] 1.15 Run `task up` against a local kind cluster and confirm the web pod reaches Running and `http://<KIND_LISTEN_ADDRESS>:18787/` returns HTTP 200.
- [ ] 1.16 Run `task test` and confirm the new web endpoint smoke check passes alongside existing hub and mcp checks.
