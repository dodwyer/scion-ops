# Implementation Steward Session 20260511t130743z-290c

Change: base-framework-1
Base branch: main
Final branch: round-20260511t130743z-290c-integration

Goal:
Implement the accepted OpenSpec change base-framework-1 from pulled main. Build the additive new UI evaluation path: choose and document concrete preview resource names and ports, scaffold a TypeScript + React + Vite mocked operator console with a small Python adapter, provide schema-faithful mocked data for overview, rounds, round detail/timeline, inbox, runtime/source health, diagnostics/raw payloads, and add Kubernetes manifests/tasks/smoke coverage for a separate preview Deployment/Service/pod on a distinct port. Preserve the existing scion-ops-web-app behavior and lifecycle. Keep the preview read-only and fixture-backed with no live Hub/MCP/Kubernetes/git/OpenSpec/model-backed reads or mutations. The implementation should leave an operator-accessible mocked data view once deployed.
