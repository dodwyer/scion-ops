#!/usr/bin/env bash
# Helpers for preparing GitHub-backed round branches before Scion starts pods.

scion_ops_load_github_token_for_branch_precreate() {
  local token_file="/run/secrets/scion-github-token/GITHUB_TOKEN"
  if [[ -z "${GITHUB_TOKEN:-}" && -r "$token_file" ]]; then
    GITHUB_TOKEN="$(cat "$token_file")"
    export GITHUB_TOKEN
  fi
}

scion_ops_github_authenticated_remote() {
  local remote="$1"
  if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    case "$remote" in
      https://github.com/*)
        printf 'https://x-access-token:%s@github.com/%s' "$GITHUB_TOKEN" "${remote#https://github.com/}"
        return
        ;;
      git@github.com:*)
        printf 'https://x-access-token:%s@github.com/%s' "$GITHUB_TOKEN" "${remote#git@github.com:}"
        return
        ;;
      ssh://git@github.com/*)
        printf 'https://x-access-token:%s@github.com/%s' "$GITHUB_TOKEN" "${remote#ssh://git@github.com/}"
        return
        ;;
    esac
  fi
  printf '%s' "$remote"
}

scion_ops_resolve_base_ref() {
  local project_root="$1"
  local base_branch="$2"
  local remote fetch_remote ref

  remote="$(git -C "$project_root" remote get-url origin 2>/dev/null || true)"
  if [[ -n "$remote" ]]; then
    scion_ops_load_github_token_for_branch_precreate
    fetch_remote="$(scion_ops_github_authenticated_remote "$remote")"
    GIT_TERMINAL_PROMPT=0 git -C "$project_root" fetch --quiet "$fetch_remote" \
      "+refs/heads/${base_branch}:refs/remotes/origin/${base_branch}" >/dev/null 2>&1 || true
  fi

  for ref in "origin/$base_branch" "$base_branch"; do
    if git -C "$project_root" rev-parse --verify --quiet "${ref}^{commit}" >/dev/null; then
      printf '%s\n' "$ref"
      return 0
    fi
  done

  return 1
}

scion_ops_export_base_branch_to_temp_root() {
  local project_root="$1"
  local base_branch="$2"
  local target_root="$3"
  local base_ref

  base_ref="$(scion_ops_resolve_base_ref "$project_root" "$base_branch")" || return 1
  mkdir -p "$target_root"
  git -C "$project_root" archive "$base_ref" | tar -x -C "$target_root"
}

scion_ops_ensure_remote_branch() {
  local project_root="$1"
  local branch="$2"
  local base_branch="$3"
  local remote push_remote base_ref

  remote="$(git -C "$project_root" remote get-url origin 2>/dev/null || true)"
  [[ -n "$remote" ]] || {
    printf 'Warning: origin remote is missing; cannot pre-create %s\n' "$branch" >&2
    return 0
  }
  push_remote="$(scion_ops_github_authenticated_remote "$remote")"

  if GIT_TERMINAL_PROMPT=0 git -C "$project_root" ls-remote --exit-code --heads "$push_remote" "$branch" >/dev/null 2>&1; then
    return 0
  fi

  if ! base_ref="$(scion_ops_resolve_base_ref "$project_root" "$base_branch")"; then
    base_ref="HEAD"
  fi

  printf 'Pre-creating round branch: %s from %s\n' "$branch" "$base_ref"
  if ! GIT_TERMINAL_PROMPT=0 git -C "$project_root" push "$push_remote" "${base_ref}:refs/heads/${branch}" >/dev/null; then
    printf 'Warning: failed to pre-create %s; Scion will try to create it during agent start\n' "$branch" >&2
  fi
}
