# Tasks

- [ ] 1.1 Add `web-rbac.yaml` to `deploy/kind/control-plane/` with ServiceAccount, Role (get/list pods, pod logs, deployments, services, pvcs), and RoleBinding for `scion-ops-web`.
- [ ] 1.2 Add `web-service.yaml` to `deploy/kind/control-plane/` as a NodePort Service on port 8787 / nodePort 30787.
- [ ] 1.3 Add `web-deployment.yaml` to `deploy/kind/control-plane/` using the `scion-ops-mcp` image, overriding entrypoint to run `scripts/web_app_hub.py`, mounting workspace and hub-dev-auth secret, and setting in-cluster env vars (`SCION_OPS_MCP_URL`, `SCION_OPS_WEB_HOST`, `SCION_DEV_TOKEN_FILE`, hub endpoint vars).
- [ ] 1.4 Add `web-rbac.yaml`, `web-service.yaml`, and `web-deployment.yaml` to `deploy/kind/control-plane/kustomization.yaml`.
- [ ] 1.5 Add the web app port mapping placeholder (`__WEB_NODE_PORT__`, `__WEB_HOST_PORT__`) to `deploy/kind/cluster.yaml.tpl`.
- [ ] 1.6 Update `scripts/kind-scion-runtime.sh` to define `WEB_NODE_PORT=30787` and `WEB_HOST_PORT`, substitute the new template placeholders, verify the web binding in the post-create check, and include the web app URL in status output.
- [ ] 1.7 Verify `kubectl apply -k deploy/kind/control-plane` applies cleanly with the new resources included.
- [ ] 1.8 Verify the web app pod reaches Ready state and the overview page is reachable at the kind host port with no DNS or hub-auth errors.
