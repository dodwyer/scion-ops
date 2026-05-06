# Workspace Persistence Model

This design defines how scion-ops should manage target project workspaces when
the Kubernetes deployment moves beyond local kind.

The product contract stays the same: an MCP client supplies a target project
and a goal, scion-ops links that project to the Hub, and Scion agents solve the
problem in Kubernetes through Hub-managed branches.

## Principles

- GitHub is the source of truth for target project content.
- `project_root` means "the checkout visible to the MCP server".
- Scion agent pods do not use the MCP checkout as their workspace. In Hub mode
  agents clone from Git, work in pod-local storage, and push result branches.
- Uncommitted editor buffers are not part of a round. Important work must be
  committed or pushed before the round starts.
- Workstation bind mounts are allowed only for the local kind development
  substrate.
- Cluster workspace cleanup must be explicit and must not delete dirty or
  unpushed work by default.

## Current kind Shape

Local kind keeps two workspace sources:

| Source | Path | Purpose | Persistence |
|---|---|---|---|
| Host workspace mount | `/workspace` | Live access to local checkouts, including scion-ops itself | Survives `task down` because it is host state |
| MCP checkout PVC | `/home/scion/checkouts/github` | GitHub repos prepared by `scion_ops_prepare_github_repo` | Deleted with the kind cluster |

The host mount is a local development convenience. It is not the cluster
workspace model.

## Cluster Shape

Cluster deployments should not mount a workstation path. The intended shape is:

| Component | Workspace responsibility |
|---|---|
| MCP image | Contains the scion-ops MCP server and repo operational scripts at a release path such as `/opt/scion-ops` |
| MCP checkout PVC | Stores target project checkouts under `/home/scion/checkouts/github/<owner>/<repo>` |
| Hub state PVC | Stores Hub records, grove links, templates, harness configs, and round metadata |
| Runtime Broker | Starts agent pods through Scion's Kubernetes runtime |
| Agent pods | Clone the target Git repo from Hub/GitHub, push branches, and discard pod-local workspace state on exit |

For a GitHub target, the operator or external agent calls
`scion_ops_prepare_github_repo(repo_url)`. The MCP server clones or reuses the
repo in its checkout PVC and returns the MCP-visible `project_root`. All
subsequent status, spec, round, and artifact calls use that returned path.

For a target already known by path, the path must still resolve inside the MCP
server's configured workspace roots. In cluster deployments that should normally
mean the checkout PVC, not a node `hostPath`.

## Lifecycle

1. Prepare the repo.
   `scion_ops_prepare_github_repo` resolves the GitHub URL, creates the owner
   and repo directory, clones using the requested HTTPS or SSH URL, validates
   that any existing checkout has the expected origin, and returns `project_root`.

2. Bootstrap the target.
   `task bootstrap -- <project_root>` or the equivalent MCP flow links the
   checkout as a Hub grove, provides the Kubernetes broker, restores shared
   credentials, and syncs templates and harness configs through the Hub pod.

3. Start the round.
   Scion starts agents through Hub mode. Agents clone from Git, create or update
   round branches, push the branch result, and write Hub records.

4. Inspect artifacts.
   MCP artifact tools inspect Hub records, pushed branches, local checkout
   state, and OpenSpec files where relevant. Hub and GitHub are the durable
   artifacts; pod-local agent workspaces are not.

5. Refresh or clean up.
   A future workspace refresh command should fetch or reset only after checking
   that the MCP checkout is clean or after an explicit force option. A future
   prune command should delete only clean, pushed, inactive checkouts by default.

## Persistent State

| State | Required beyond kind | Restore policy |
|---|---|---|
| Hub database/state PVC | yes | Back up or retain across control-plane upgrades |
| Stable Hub ID | yes | Keep as deployment config so Hub-scoped secrets remain addressable |
| Broker HMAC credential Secret | yes | Recreate through native `scion broker register` or restore from backup |
| Hub auth/session Secrets | yes | Replace kind dev auth with the supported production auth model before cluster support |
| Hub-scoped model credentials | yes | Restore from operator-provided Kubernetes Secret or bootstrap source |
| Templates and harness configs | yes | Re-sync from the scion-ops release image or repo source during bootstrap |
| MCP checkout PVC | yes for convenience, no as source of truth | Retain for active workspaces; rebuild from Git if lost |
| Agent pod workspaces | no | Ephemeral by design |
| Round output branches | yes | Pushed to GitHub |

The MCP checkout PVC may contain `.scion/grove-id` files and local spec files
before they are pushed. It should be treated as useful state, but GitHub and Hub
must remain the durable record for completed work.

## Destroy And Cleanup

Local kind keeps the simple contract:

```bash
task down
```

That deletes the kind cluster and all cluster-local PVCs and Secrets. Host
workspace checkouts survive because they are outside the cluster.

For cluster deployments, use two explicit modes:

| Mode | Behavior |
|---|---|
| Teardown | Delete workloads, Services, ConfigMaps, and RBAC while retaining labeled PVCs and Secrets |
| Purge | Delete the namespace or all labeled state after an explicit confirmation |

All persistent resources should carry the scion-ops labels already used by the
kind manifests, plus any future retention labels needed to distinguish
rebuildable state from state that needs backup. Cleanup commands should refuse
to delete a checkout that has uncommitted changes, unpushed branches, or an
active Hub round unless forced.

## Implementation Implications

This issue is design-only. Implementation should be split into later PRs:

- Package the MCP server source and operational scripts into the MCP image for
  cluster deployments, instead of relying on `/workspace/scion-ops`.
- Add a cluster overlay that omits the kind workspace `hostPath` and uses the
  MCP checkout PVC as the target workspace root.
- Add workspace list, refresh, and prune operations with dirty-workspace guards.
- Add documented teardown and purge tasks once the non-kind deployment target
  exists.
