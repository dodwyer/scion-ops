# Kubernetes Packaging Decision

Date: 2026-05-06

Issue: #57

## Decision

Keep scion-ops Kubernetes resources as native manifests managed by Kustomize for
the current local kind deployment.

Do not introduce Helm yet. If the packaging model grows beyond Kustomize, move
to a Helm chart managed by helmfile, not ad hoc `helm install` commands.

The operator interface remains:

```bash
task up
task test
task down
```

Packaging changes must not change that top-level contract.

## Why Kustomize Fits Now

The current deployment has one supported runtime target: local kind. The
resource set is small, native, and directly inspectable:

- namespace and runtime RBAC
- Hub Deployment, Service, and PVC
- dedicated Runtime Broker Deployment and RBAC
- MCP Deployment, Service, and checkout PVC
- ConfigMaps generated from checked-in files
- a checked-in no-auth smoke agent config

Kustomize keeps these resources deployable with:

```bash
kubectl apply -k deploy/kind
kubectl apply -k deploy/kind/control-plane
```

That matches the current need better than a chart values API. It also keeps the
manifest files referenceable while the control-plane shape is still changing.

## Helm Review Triggers

Re-evaluate packaging when one or more of these becomes true:

| Trigger | Why it matters |
|---|---|
| More than one supported non-kind cluster target exists | Repeated overlays may need a stable values schema |
| Operators need install, diff, upgrade, and rollback lifecycle as a first-class workflow | Helm plus helmfile provides a standard release workflow |
| Configuration becomes mostly parameterized rather than environment-specific overlays | A chart values API may become clearer than Kustomize patches |
| The same resource changes need to be applied across several environments | helmfile can coordinate shared chart versions and per-environment values |
| State retention policies need explicit release semantics | Helm hooks and helmfile ordering may be useful once stateful upgrades are real |

These are not triggers by themselves:

- adding a small number of native Kubernetes resources
- adding another ConfigMap generated from a checked-in file
- keeping local kind ports or workspace mounts separate from future cluster
  overlays
- wanting a one-line user command, because `task` already provides that

## Required Helm Shape If We Move

If the triggers are met, the accepted shape is:

```text
deploy/
  chart/scion-ops/
    Chart.yaml
    values.yaml
    templates/
  helmfile.yaml
  environments/
    kind.yaml
    cluster.yaml
```

Rules for that migration:

- `task up`, `task test`, and `task down` remain the supported entry points.
- Helm is invoked through helmfile tasks only.
- No ad hoc `helm install`, `helm upgrade`, or `helm uninstall` commands become
  part of docs or scripts.
- Values files are checked in for non-secret defaults.
- Secrets are referenced from Kubernetes Secrets or external secret tooling,
  not embedded in chart values.
- `helm template` output must be easy to inspect during review.
- Kustomize and Helm must not both own the same live resource set.

## Guardrails

Kubernetes resources must stay source-controlled and reviewable. Scripts should
not embed literal Kubernetes YAML bodies when a native manifest, Kustomize
generator, or chart template is the clearer source of truth.

The packaging layer should not decide runtime behavior. Runtime behavior stays
in Scion, the Hub, the broker, MCP, and the checked-in task lifecycle.

## Current Follow-up

No implementation change is needed for this decision. The next packaging review
should happen when scion-ops adds a non-kind cluster deployment target or when
the control-plane configuration starts duplicating across overlays.
