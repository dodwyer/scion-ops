# Proposal: Use NiceGUI

## Summary

Replace the existing web UI frontend with a NiceGUI-based operator console for scion-ops. The new frontend should start from a fresh interface structure while preserving the current read-only operational model, browser-facing JSON and health contracts, deployment compatibility, and automatic update behavior.

## Motivation

The web UI has grown around a script-oriented HTTP server and accumulated view structure. Operators need a concise, action- and context-related console that makes the current state obvious by default, while keeping deeper troubleshooting one level down. NiceGUI provides a Python-native UI layer that fits the existing Python operational tooling and can produce a more deliberate interface without inventing a separate JavaScript application stack.

The replacement should apply Laws of UX principles from https://lawsofux.com/ as design constraints: reduce cognitive load, favor recognition over recall, group related state, keep common actions and context close to the information they affect, and avoid visual or interaction patterns that slow repeated monitoring.

## Scope

In scope:

- Rebuild the browser UI as a NiceGUI frontend served by the web app control-plane component.
- Start the frontend information architecture from a fresh operator-console design rather than preserving current page layout.
- Preserve existing read-only behavior and avoid round-starting, retrying, aborting, deleting, git-writing, OpenSpec-writing, or Kubernetes-mutating controls.
- Preserve the existing browser-facing JSON snapshot, round detail, live update, and health contracts used by tests, smoke checks, and automation.
- Preserve runtime and deployment compatibility with the current host-side script path and kind control-plane deployment shape.
- Provide a concise operator overview by default, with in-depth troubleshooting and raw diagnostic detail one interaction level down.
- Include Laws of UX design constraints for layout, hierarchy, interaction feedback, progressive disclosure, and accessibility.

Out of scope:

- Adding write operations or workflow orchestration controls to the web UI.
- Changing Hub, MCP, Kubernetes, OpenSpec, or live-update source-of-truth contracts.
- Removing or renaming existing JSON or health endpoints that external checks rely on.
- Introducing a separate JavaScript single-page application build pipeline.
- Production authentication, authorization, or user-specific personalization.

## Success Criteria

- Operators can open the NiceGUI app and immediately see control-plane readiness, live update freshness, active or blocked round context, and next relevant inspection targets.
- Detailed source errors, raw payloads, validation output, branch evidence, and runner diagnostics are available one level below the overview or affected round, without crowding the default screen.
- Existing JSON and health endpoints remain compatible with current no-spend tests and kind smoke checks.
- The NiceGUI app runs in the existing local and kind deployment paths with the same source-of-truth, auth, workspace, and service conventions.
- The interface remains read-only during page load, live updates, reconnect, fallback polling, and troubleshooting inspection.
- Visual and interaction design demonstrably considers Laws of UX principles and avoids decorative, marketing-style, or high-cognitive-load presentation.
