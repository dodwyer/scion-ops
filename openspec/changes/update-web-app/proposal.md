# Proposal: Update Web App

## Summary

Align the scion-ops web app hub (`scripts/web_app_hub.py`) with recent changes
to the MCP service (`mcp_servers/scion_ops.py`) and include the web app as a
managed deployment in the kustomize/kind control-plane install.

## Motivation

The MCP service received updates that changed port handling, verdict
normalisation, and final review outcome fields. The web app imports
`mcp_servers.scion_ops` directly and carries its own workarounds that are now
redundant or inconsistent with the updated module. Additionally the web app
currently runs only as a local developer task (`task web:hub`) and is not
present in the kind control-plane deployment, so operators cannot access it
through the standard cluster port mappings.

## Scope

In scope:

- Remove the `SCION_OPS_MCP_PORT` env-var workaround in `web_app_hub.py` that
  pre-dates the `_env_port()` helper now present in `scion_ops.py`.
- Expose `final_failure_classification` and `final_failure_evidence` in the
  round detail view, using the fields now returned by `_final_review_outcome`.
- Update `CONTROL_PLANE_NAMES` in `web_app_hub.py` to include the web app
  deployment name so the runtime readiness view reports itself correctly.
- Add Kubernetes Deployment and NodePort Service manifests for the web app.
- Add the web app resources to `deploy/kind/control-plane/kustomization.yaml`.
- Add a host port mapping for the web app in `deploy/kind/cluster.yaml.tpl`.
- Propagate the web app port variables through `scripts/kind-scion-runtime.sh`
  and `Taskfile.yml` following existing hub/mcp patterns.

Out of scope:

- Changing the web app's read-only contract or adding write operations.
- Introducing a separate container image; the web app reuses the existing
  `scion-ops-mcp` image and workspace hostPath mount.
- Modifying Scion Hub, broker, or MCP service behaviour.
- Adding authentication or multi-user roles to the web app.

## Success Criteria

- The web app can be deployed by running the existing control-plane apply task
  without additional manual steps.
- Operators can reach the web app at the documented host port after a standard
  kind cluster setup.
- The runtime view in the web app correctly reflects the web app deployment's
  own readiness.
- The round detail view surfaces `final_failure_classification` and
  `final_failure_evidence` when present in outcome data.
- The `SCION_OPS_MCP_PORT` env-var workaround is removed; port resolution
  relies on `_env_port` in `scion_ops.py`.
- Existing static checks and smoke tests continue to pass.

## Assumptions

- The web app listens on `SCION_OPS_WEB_PORT` (default `8787`) and
  `SCION_OPS_WEB_HOST` (default `0.0.0.0` in-cluster).
- NodePort `30787` is used for the web app service, consistent with the
  existing hub (30090) and mcp (30876) convention.
- The kind cluster host port for the web app follows the existing
  `SCION_OPS_KIND_*` variable naming convention.
- No changes to the `scion-ops-mcp` container image are required; the web app
  entrypoint differs only in the script path.
