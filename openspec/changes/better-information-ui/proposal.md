# Proposal: Better Information UI

## Summary

Improve the operator-facing information design for the web app hub overview and selected-round timeline. The default UI should remove noisy or irrelevant details, show the current action, handoff target, and reason for handoff, preserve repeated back-and-forth exchanges between the same agents, and use current NiceGUI component patterns in a responsive layout that does not overflow on desktop or mobile.

## Motivation

The current operator overview and timeline expose a large amount of information without enough prioritization. Operators need to understand what is happening, who owns the next step, and why a handoff occurred. Repeated exchanges between agents are also meaningful operational evidence, so collapsing rows by agent can hide important context.

This change defines the information contract and layout expectations before implementation, so the UI can become more useful without changing the app's read-only runtime behavior or source-of-truth boundaries.

## Scope

In scope:

- Operator overview content and selected-round timeline content represented by `scripts/web_app_hub.py`.
- Timeline entry normalization for action, handoff, and reason-for-handoff fields.
- Preservation of duplicate same-agent or same-agent-pair handoff rows when the backing source provides distinct entries.
- Moving raw payloads, logs, and low-level diagnostics one interaction deeper.
- Modern NiceGUI component usage for overview, round detail, timeline, and drill-in controls.
- Desktop and mobile layout behavior, including no horizontal overspill for representative content.

Out of scope:

- Authentication and authorization changes.
- Non-operator views outside the web app hub surfaces.
- New round mutation controls or other write operations.
- Changes to Hub, MCP, Kubernetes, or OpenSpec source contracts beyond backward-compatible display fields.
- Replacing the read-only live-update behavior.

## Success Criteria

- The overview highlights the highest-value operator status and next inspection target instead of presenting a long undifferentiated information dump.
- Selected-round timeline rows show action, handoff, and reason for handoff when source data supports them.
- Multiple handoffs involving the same agent or same pair of agents remain visible as separate rows when they have distinct source ids, timestamps, or sequence positions.
- Raw JSON, long logs, runner output, and low-level diagnostic payloads are accessible one interaction deeper without dominating default screens.
- NiceGUI views use first-class components such as tables, timeline/list rows, tabs, expansion panels, chips/badges, splitters, drawers, and dialogs where appropriate.
- Desktop and mobile viewport checks show no overlapping controls, clipped key text, or page-level horizontal overflow.
