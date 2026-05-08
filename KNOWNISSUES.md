# Known Issues

Track intentional exceptions, unresolved risks, and design decisions that need
revisit before they become hidden assumptions.

## Kubernetes Packaging Review Trigger

Issue: #57

Decision: keep the supported local Kubernetes deployment as native manifests
and Kustomize.

Reason: the first implementation target is a local kind environment with a
small resource set, minimal templating requirements, and an existing
`kubectl apply -k deploy/kind` workflow. This keeps the day-zero path
inspectable and avoids designing a chart values API before the resource model is
proven. Kubernetes is the only supported deployment path; this decision is about
packaging, not whether the control plane runs in Kubernetes.

Constraint: move to Helm managed through helmfile when one of these is true:
configuration expands beyond the local overlay, repeated overlays start
duplicating operational choices, a values schema becomes necessary, or install,
upgrade, and rollback lifecycle needs to be driven from one operator command.

Exit criteria: re-open the packaging decision when the triggers above are met,
especially when a non-kind cluster deployment target is added.

## kind Hub Dev Auth

Issue: #54

Decision: the in-kind Hub runs `scion server start` with explicit Hub/Web
components and dev auth enabled. `task bootstrap` restores the dev-auth token
as `scion-hub-dev-auth`, restores the web session signing secret as
`scion-hub-web-session`, and sets Hub `TMPDIR` to the Hub PVC so filesystem
session data survives Hub pod restarts.

Reason: `--production` prevents workstation defaults from starting extra
components, while `--dev-auth` keeps the local kind Hub usable before the
project supports a non-kind production auth model.

Constraint: this is local-kind only. Browser session continuity depends on
`task bootstrap` having restored the session Secret and restarted Hub.

Exit criteria: replace dev-only auth/session behavior with the supported
production auth model before supporting non-kind Kubernetes deployments.

## Local kind MCP Workspace HostPath

Issue: #56

Decision: local kind clusters mount the host `scion-ops` checkout into the kind
node with a kind `extraMount`, so the MCP pod can mount that node path with
Kubernetes `hostPath`. This remains a local development shortcut only. The
accepted cluster workspace design is MCP-managed GitHub checkouts on persistent
storage, with agent pods cloning from Git through Hub mode.

Reason: the MCP server needs live repo access for git, task, Scion, and
artifact inspection. In kind, pod `hostPath` volumes see the node container
filesystem, so the host checkout must be mounted into the node before any MCP
Deployment can use it. For clusters beyond kind, the same capability should be
provided by a checkout PVC rather than a workstation bind mount.

Constraint: this is local-kind only and is not an agent workspace pattern. Do
not use workstation bind mounts for non-kind clusters or for Scion agent
runtime pods.

Exit criteria: keep hostPath confined to kind manifests. Before adding a
non-kind deployment target, package MCP without a `/workspace/scion-ops`
source mount and make the MCP checkout PVC the target project workspace root.

## kind Hub Dev Auth Secret Restore

Issue: #53

Decision: the local kind Hub remains dev-auth based, but `task bootstrap`
mirrors the active Hub dev-auth token into the `scion-hub-dev-auth`
Kubernetes Secret. The MCP Deployment reads that Secret through
`SCION_DEV_TOKEN_FILE` and does not mount the Hub PVC.

Reason: the Hub still generates and persists the local dev token in its own
state, but MCP should consume an explicit Kubernetes auth resource rather than
read Hub storage. `task kind:hub:auth-export` falls back to the Hub pod only
before bootstrap has restored the Secret.

Constraint: this is local-kind only. Dev auth remains unsuitable for
non-kind Kubernetes deployments.

Exit criteria: replace dev auth with the supported production auth model before
supporting non-kind Kubernetes deployments.

## kind Dedicated Broker Registration

Issue: #55

Decision: the in-kind Runtime Broker runs as its own `scion-broker`
Deployment. Bootstrap uses Scion's native `broker register` flow when the Hub
does not already show the broker as connected, stores the resulting HMAC
credential JSON in the `scion-broker-credentials` Kubernetes Secret, restarts
the broker, and waits for the Hub control-channel connection.

Reason: the Hub and Runtime Broker now follow Scion's separate-process Hub mode
instead of the embedded server shortcut, while broker credentials remain
restorable through Kubernetes-managed state.

Constraint: this remains a local-kind control-plane shape. The broker API binds
inside the broker pod; Hub dispatch normally reaches it through Scion's
control-channel path rather than a public Service.

Exit criteria: for non-kind clusters, define the longer-lived broker credential
rotation and backup policy alongside the workspace persistence model.

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
