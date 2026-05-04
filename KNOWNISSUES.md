# Known Issues

Track intentional exceptions, unresolved risks, and design decisions that need
revisit before they become hidden assumptions.

## Kustomize-First kind Control Plane

Issue: #15

Decision: start the optional all-in-kind Scion control-plane deployment with
native Kubernetes manifests and Kustomize, not Helm.

Reason: the first implementation target is a local kind environment with a
small resource set, minimal templating requirements, and an existing
`kubectl apply -k deploy/kind` workflow. This keeps the day-zero path
inspectable and avoids designing a chart values API before the resource model is
proven.

Constraint: if configuration expands beyond a small local overlay, or if we
need install/upgrade lifecycle from the console, move to Helm managed through a
helmfile rather than ad hoc `helm install` commands.

Exit criteria: Kustomize remains acceptable only while the control-plane config
can stay simple, native, and reproducible from this repo.

## kind Hub Dev Auth

Issue: #15

Decision: the first in-kind Hub slice runs `scion server start` with explicit
Hub/Web components and dev auth enabled.

Reason: `--production` prevents workstation defaults from starting extra
components, while `--dev-auth` keeps the local kind Hub usable before OAuth,
broker credentials, and secret restore are implemented.

Constraint: this is local-development only. The web session secret is
auto-generated on pod start, so browser sessions do not survive Hub pod
restarts.

Exit criteria: replace dev-only auth/session behavior with Kubernetes Secret
restore before using the kind control plane outside local testing.
