# Known Issues

Track intentional exceptions, unresolved risks, and design decisions that need
revisit before they become hidden assumptions.

## Kustomize-First Kubernetes Control Plane

Issue: #31

Decision: keep the supported local Kubernetes deployment as native manifests
and Kustomize, not Helm.

Reason: the first implementation target is a local kind environment with a
small resource set, minimal templating requirements, and an existing
`kubectl apply -k deploy/kind` workflow. This keeps the day-zero path
inspectable and avoids designing a chart values API before the resource model is
proven. Kubernetes is the only supported deployment path; this decision is
about packaging, not whether the control plane runs in Kubernetes.

Constraint: if configuration expands beyond a small local overlay, or if we
need install/upgrade lifecycle from the console, move to Helm managed through a
helmfile rather than ad hoc `helm install` commands.

Exit criteria: Kustomize remains acceptable only while the control-plane config
can stay simple, native, and reproducible from this repo.

## kind Hub Dev Auth

Issue: #31

Decision: the first in-kind Hub slice runs `scion server start` with explicit
Hub/Web components and dev auth enabled.

Reason: `--production` prevents workstation defaults from starting extra
components, while `--dev-auth` keeps the local kind Hub usable before OAuth,
broker credentials, and secret restore are implemented.

Constraint: this is local-kind only. The web session secret is
auto-generated on pod start, so browser sessions do not survive Hub pod
restarts.

Exit criteria: replace dev-only auth/session behavior with Kubernetes Secret
restore before supporting non-kind Kubernetes deployments.

## kind MCP Workspace HostPath

Issue: #31

Decision: local kind clusters mount the host `scion-ops` checkout into the kind
node with a kind `extraMount`, so the MCP pod can mount that node path with
Kubernetes `hostPath`.

Reason: the MCP server needs live repo access for git, task, Scion, and
artifact inspection. In kind, pod `hostPath` volumes see the node container
filesystem, so the host checkout must be mounted into the node before any MCP
Deployment can use it.

Constraint: this is local-kind only and is not an agent workspace pattern. Do
not use workstation bind mounts for non-kind clusters or for Scion agent
runtime pods.

Exit criteria: for non-local clusters, replace this with a cloned workspace or
persistent workspace volume managed by explicit bootstrap/restore tasks.

## kind MCP Hub Dev Token Sharing

Issue: #31

Decision: the local kind MCP Deployment mounts the Hub PVC read-only and reads
the Hub dev-auth token from `/hub-state/dev-token`.

Reason: the current kind Hub slice is intentionally dev-auth based and does not
yet restore a Kubernetes Secret for Hub auth material. Sharing the generated
token lets the MCP server use the Hub HTTP API without introducing a separate
bootstrap system in this slice.

Constraint: this is local-kind only. The MCP pod can read Hub state from
the PVC, so it must be treated as a privileged control-plane component.

Exit criteria: replace PVC token sharing with explicit Secret restore before
supporting non-kind Kubernetes deployments.

## kind Co-Located Broker First

Issue: #31

Decision: the first in-kind Runtime Broker slice runs inside the Hub pod by
enabling Scion's co-located Hub+broker server mode.

Reason: a separate broker Deployment needs a reliable HMAC credential bootstrap
or restore path before it can join Hub mode safely. The co-located Scion server
path already creates the broker record and broker secret in Hub state, which is
enough for the local kind control plane to prove Kubernetes runtime access
without custom registration plumbing.

Constraint: this is a local-kind control-plane shape. The broker binds
to loopback inside the Hub pod and is not exposed as a Kubernetes Service.

Exit criteria: add a separate broker Deployment only after the project has an
explicit broker credential restore or registration bootstrap flow.

## kind Hub Local Storage Uploads

Issue: #29

Decision: keep the kind control-plane smoke on an inline `generic` harness
config, but use `task bootstrap` as the normal template and harness restore
path for rounds.

Reason: the current kind Hub uses Scion local storage on the Hub PVC. When a
host CLI talks to that Hub through a port-forward, template and harness-config
sync can receive pod-local upload paths such as `/home/scion/.scion/storage/...`
that are not writable or meaningful from the host. That is not a supported
Kubernetes bootstrap pattern.

Constraint: do not sync scion-ops templates or harness configs to the kind Hub
from the host CLI. `task bootstrap` copies the files into the Hub pod and runs
Scion sync commands there, where `/home/scion/.scion/storage` is meaningful.

Exit criteria: remove the inline generic smoke fallback only after spending
subscription model usage in smoke tests is acceptable.

## Subscription-Backed Kubernetes Rounds

Issue: #29

Decision: `task bootstrap` restores shared Hub-scoped credentials, Hub harness
configs, and Hub global scion-ops templates before subscription-backed rounds.
`task test` remains a no-auth smoke to avoid spending model usage in the normal
health check.

Reason: the product goal is a one-line Scion consensus round through the
Kubernetes-hosted Hub and MCP server, but baking subscription credentials into
images or relying on host-local upload paths would create hidden state and a
non-reproducible setup.

Constraint: target projects must be visible inside the MCP pod workspace mount
and should have important local work committed or pushed before a round starts.
Hub/Kubernetes agents work from git branches, not uncommitted editor buffers.

Exit criteria: a Claude/Codex/Gemini consensus round passes through the
Kubernetes Hub from a Zed MCP request against the selected target project.

## Repo-Owned Scion Runtime Patches

Issue: #67

Decision: keep the Scion runtime fixes required by scion-ops as patch files
under `patches/scion/`, and have build entry points ensure those patches are
present in the configured local Scion checkout before building images or Hub
dev binaries.

Reason: the tested Kubernetes round path currently depends on runtime behavior
that is not guaranteed by an arbitrary upstream Scion checkout. The user does
not want this work pushed to public Scion repositories, so scion-ops must own a
reproducible local build path instead of relying on hidden workstation edits.

Constraint: this mutates the configured local Scion checkout. It is acceptable
only for the local kind product path, and failures must be explicit when a
patch cannot apply cleanly.

Exit criteria: either the required behavior is available in the default Scion
source used by scion-ops builds, or scion-ops vendors/pins a Scion source in a
way that no longer requires patching a separate checkout.
