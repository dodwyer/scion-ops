# Design: Web UI Theme

## Overview

The web UI should look and behave like an operations console. The theme should make live Scion state easier to scan, compare, and diagnose. Visual choices should support the existing views rather than becoming a separate presentation layer.

The current app is intentionally read-only and source-driven. The theme should preserve that model: status, validation, final-review, branch, MCP, Hub, and Kubernetes data remain the primary content, while styling clarifies priority and severity.

## Ensure all design decisions follow this

- https://lawsofux.com/
- Use NiceGUI

## Visual Direction

Use a neutral, restrained palette as the default surface:

- off-white or light gray page background;
- white or near-white panels;
- dark neutral body text;
- muted neutral secondary text;
- subtle borders and row dividers;
- semantic accents reserved for operational states.

Avoid decorative gradients, ornamental backgrounds, large hero sections, marketing-style cards, or playful illustration. Cards should frame individual repeated items or diagnostic panels only; page sections should stay unframed or use simple full-width content areas.

## Semantic State Treatment

Status color should be semantic and consistent:

- healthy, ready, completed, accepted, and connected use a green accent;
- running and live activity use a blue accent;
- waiting, stale, observed, fallback polling, reconnecting, and degraded use an amber accent;
- blocked, failed, unavailable, error, and changes requested use a red accent;
- unknown uses a neutral treatment.

Color must not be the only signal. State labels, status dots or icons, and source-specific error text should remain visible. Blocked or failed state should be prominent enough to scan in tables without overwhelming unrelated healthy data.

## Layout And Density

The theme should favor compact, predictable layout:

- top navigation remains simple and persistent;
- overview checks use compact summary panels;
- rounds use a table or table-like layout optimized for comparison;
- round detail preserves a two-column diagnostic layout on wider screens and collapses cleanly on narrow screens;
- inbox and runtime views keep source and timestamp data visible without excessive whitespace.

Spacing should be consistent and modest. The implementation should not use oversized typography inside operational panels. Long identifiers, branch names, JSON, runner output, and validation messages should wrap or scroll within stable containers without forcing layout shifts.

## Typography And Data Display

Use a system UI font for normal text and a monospace font for identifiers, branch refs, JSON, logs, and code-like values. Text hierarchy should be clear but restrained:

- page title and section headings should be smaller than marketing hero type;
- table headers and metadata labels should be muted but readable;
- important status and outcome labels should have enough weight to scan quickly;
- line height should support reading dense operational text.

Metadata pills may be used for compact facts such as role, template, harness, phase, activity, and branch source. They should use small radii and neutral borders, with semantic color reserved for actual state.

## Accessibility And Responsiveness

The theme should meet basic accessibility expectations for an internal operations tool:

- text and status accents should have sufficient contrast on their backgrounds;
- focus states should be visible for navigation and buttons;
- buttons and table rows should have predictable hover and active states;
- content should not overlap at mobile or desktop widths;
- narrow screens should collapse columns, wrap metadata, and keep essential status and round identifiers visible.

The implementation should verify at least one desktop and one narrow viewport. The check can be automated, screenshot-based, or fixture-driven, but it should confirm that primary views render without blank screens, overlapping controls, or unreadable status text.

## Verification Strategy

Implementation should include no-spend verification:

- static or fixture tests confirming semantic status classes map to the expected state categories;
- rendered HTML or browser checks for overview, rounds, round detail, inbox, and runtime views using representative healthy and degraded data;
- responsive checks for desktop and narrow widths;
- contrast or style checks sufficient to catch accidental decorative gradients, missing focus states, or one-note color use;
- existing web app tests to confirm theming does not alter read-only behavior or source-of-truth semantics.
