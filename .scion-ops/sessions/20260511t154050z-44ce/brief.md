# Implementation Steward Session 20260511t154050z-44ce

Change: wire-new-ui-1
Base branch: main
Final branch: round-20260511t154050z-44ce-integration

Goal:
Implement OpenSpec change wire-new-ui-1: wire the separate React/Vite new UI to live read-only operational data from Hub, MCP, Kubernetes, git, and OpenSpec sources using an initial snapshot plus push-based browser updates. Preserve fixture mode only as explicit fallback, keep the existing UI separate and unchanged, include connection health/staleness/reconnect behavior, and add focused contract/frontend/read-only/coexistence verification.
