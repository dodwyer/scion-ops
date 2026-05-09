# Tasks

- [ ] 1.1 Remove the `SCION_OPS_MCP_PORT` env-var workaround from `scripts/web_app_hub.py` (lines that check and delete the env var before importing `scion_ops`).
- [ ] 1.2 Add `scion-ops-web` to `CONTROL_PLANE_NAMES` in `scripts/web_app_hub.py`.
- [ ] 1.3 Surface `final_failure_classification` and `final_failure_evidence` in the round detail HTML and JSON response in `scripts/web_app_hub.py`.
- [ ] 1.4 Run `uv run scripts/test-web-app-hub.py` and confirm tests pass with the changes from 1.1–1.3.
- [ ] 2.1 Create `deploy/kind/control-plane/web-service.yaml` (NodePort, port 8787, nodePort 30787).
- [ ] 2.2 Create `deploy/kind/control-plane/web-deployment.yaml` (reuses `scion-ops-mcp:latest` image, runs `scripts/web_app_hub.py`, `SCION_OPS_WEB_HOST=0.0.0.0`, `SCION_OPS_WEB_PORT=8787`).
- [ ] 2.3 Add `web-service.yaml` and `web-deployment.yaml` to `deploy/kind/control-plane/kustomization.yaml` resources.
- [ ] 2.4 Add the web app port mapping placeholder to `deploy/kind/cluster.yaml.tpl` (`containerPort: __WEB_NODE_PORT__`, `hostPort: __WEB_HOST_PORT__`).
- [ ] 2.5 Add `WEB_HOST_PORT` and `WEB_NODE_PORT` variables and sed substitution to `scripts/kind-scion-runtime.sh`, following the existing hub/mcp pattern.
- [ ] 2.6 Add `SCION_OPS_KIND_WEB_PORT` to the `vars` block in `Taskfile.yml`.
- [ ] 2.7 Update port-binding validation in `scripts/kind-scion-runtime.sh` to include the web node port check.
- [ ] 3.1 Run `task lint` (static checks) and confirm no Python parse errors across all relevant scripts.
- [ ] 3.2 Verify `task kind:control-plane:apply` applies cleanly with the new web resources on a running kind cluster (or confirm via dry-run that kustomize renders valid manifests).
