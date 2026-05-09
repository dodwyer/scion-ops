# Tasks

- [ ] 1.1 Confirm the OpenSpec view fits the existing read-only hub layout and does not duplicate any state from `scripts/web_app_hub.py`.
- [ ] 1.2 Add a backend endpoint that returns active and archived OpenSpec changes plus optional validator output for a selected change, sourced from the existing scion-ops `spec_status` and `validate_spec_change` helpers.
- [ ] 1.3 Add the OpenSpec list view in the hub frontend with artifact completeness indicators, archive section, and consistent empty/stale/degraded states.
- [ ] 1.4 Add the OpenSpec detail panel that shows the validator outcome, validator source identifier, and structured errors and warnings when present.
- [ ] 1.5 Add a round-detail OpenSpec reference that uses the round's existing structured target-change metadata first and only falls back to text-derived references when no structured field exists.
- [ ] 1.6 Reuse the existing refresh button and interval; do not introduce a new polling rate or a new push channel for this view.
- [ ] 1.7 Add focused tests covering: empty project (no changes), an in-progress change with missing artifacts, a fully populated change with successful validation, a change with validator failures, and an archived change appearing under the archive section.
- [ ] 1.7.1 Add a test proving the round-detail OpenSpec reference uses the structured target-change field when present and is absent when no structured field is available.
- [ ] 1.7.2 Add a test proving the OpenSpec view does not invoke any write or state-changing scion-ops helper during normal load and refresh.
- [ ] 1.8 Verify the change with the repository's standard static checks and the no-spend control-plane checks and confirm existing build-web-app-hub tests still pass.
