# KAIROS UX Contract

## Scope

This contract covers the KAIROS landing-to-dashboard experience. Product facts and model behavior come from `README.md`; visual intent and tokens come from `DESIGN.md`.

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Select/Listbox | Native HTML select in `LiveDashboard` | This contract + supported browser behavior | native only; operating-system popup geometry is accepted | keyboard selection + browser open state |
| Form | React component state in upload and live-capture forms | API contract in `react-ui/src/api/client.js` | traffic upload / passive live session | build + success/error/cancel browser flow |
| Scrollbar | Global rules in `react-ui/src/styles.css` | `DESIGN.md` token mapping | stable-gutter table and narrow navigation geometry | computed style + overflow browser check |
| Theme | Root `data-theme` set by `App.jsx` | operating-system preference, then persisted `kairos-theme` choice | matte dark / bright graphite | keyboard toggle + reload persistence + visual browser check |

## Workflow behavior

- Upload accepts one CSV, PCAP, or PCAPNG file up to 750 MiB. Selection validates type, size, and empty files before submission.
- Analysis prevents duplicate submission, exposes a stable busy state, supports cancellation, preserves the selected file after failure, and focuses the returned result summary after success.
- The bundled sample uses the same forecast request path as a user-selected file.
- Forecast results name the calibrated 10/30/60-second temporal forecast as primary. The immediate GNN-Transformer output is shown only as a diagnostic disclosure.
- Live capture is passive only. Starting and stopping remain explicit actions; errors remain inline and do not clear entered settings.
- Native interface selection is intentional because popup geometry is not product-owned. Labels remain associated and native keyboard behavior is preserved.

## Feedback and recovery

Errors are persistent inline alerts with a concrete recovery instruction. No browser-native alert, confirm, or prompt is used. Loading keeps primary action geometry stable. Empty results tell the analyst how to start.

## Navigation and responsive behavior

The root URL opens the landing page. `#dashboard` opens the operational console directly, its in-page forecast/evidence/live-capture anchors remain on that surface, and the dashboard brand returns to `#home`. Browser Back after entering the dashboard returns to the landing page.

The dashboard uses a compact top navigation with in-page landmarks. Its primary reading order is traffic input, validated forecast, forecast evidence, then optional live capture. Live capture uses native disclosure semantics and remains collapsed until requested. Both route groups scroll naturally and data tables own horizontal overflow.

The theme switch remains available at every viewport. Its label always names the destination mode, its icon is decorative, and changing appearance never changes forecast data or semantic status meaning.

## Accessibility

The target is WCAG 2.2 AA. Native semantics, visible focus, reduced-motion handling, high-contrast compatibility, keyboard upload activation, and a non-drag upload path are required.

## Route document title policy

The landing route sets `KAIROS — Predictive network defence`; the operational route sets `Attack forecast — KAIROS`. Loading and API errors remain states within the dashboard and never expose traffic identifiers in the browser title.
