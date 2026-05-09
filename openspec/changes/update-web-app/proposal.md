# Proposal: Update Web App

## Summary

Align the scion-ops web app hub with the in-cluster MCP service configuration and include it in the kind/kustomize control-plane deployment. The web app was delivered as a script but was never deployed as a Kubernetes workload alongside the hub, broker, and MCP components it monitors.

## Motivation

The MCP service was aligned to use in-cluster service discovery (`http://scion-hub:8090`), scion dev-auth token injection from a mounted secret, and a well-structured Kubernetes deployment with RBAC. The web app shares the same runtime dependencies (Hub API, MCP, Kubernetes kubectl access) but still carries a hardcoded local development IP for the MCP URL and runs only as a local script. This creates a gap between what operators can run locally and what is available in the kind cluster, making the web hub inaccessible from the managed control plane.

## Scope

In scope:

- A Kubernetes Deployment for the web app hub that mirrors the environment, auth, and secret mounting conventions used by the MCP deployment.
- A Kubernetes Service exposing the web app port within the cluster.
- RBAC resources scoped to the web app's read-only kubernetes-status and hub-auth access needs.
- Addition of the web app manifests to the kind control-plane kustomization.
- Correction of the MCP URL default so the web app resolves the in-cluster MCP service rather than a hardcoded development IP.
- Correction of the default listening host to `0.0.0.0` for in-cluster operation.

Out of scope for this change:

- Adding write operations, authentication, or multi-user roles to the web app.
- Changes to the MCP server itself or the scion Hub.
- Changing the web app feature set or data sources.
- Building a separate Docker image if the existing scion-ops-mcp image already satisfies all runtime dependencies.

## Success Criteria

- The web app runs as a Kubernetes Deployment in the `scion-agents` namespace alongside the other control-plane components.
- The web app resolves the scion-ops-mcp service by in-cluster DNS name.
- The web app authenticates to the Hub using the same dev-auth secret mounted by the MCP deployment.
- A `kubectl apply -k deploy/kind/control-plane` includes the web app without additional manual steps.
- The web app can be reached through the host port or Service from the kind host.

## Unresolved Questions

- The web app uses the scion-ops-mcp image's Python environment (imports `mcp_servers.scion_ops`). Confirmation that the existing `scion-ops-mcp` image is sufficient avoids adding a new image-build target. Implementation should verify this and document the decision.
- Port exposure strategy (NodePort, HostPort, or kind extraPortMappings) should match the existing convention used for the hub web port.
