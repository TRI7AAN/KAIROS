---
version: beta
name: "KAIROS"
description: "A matte-black operational console for explainable network-attack forecasting."
colors:
  canvas: "#0B0B0C"
  sidebar: "#0D0D0F"
  surface: "#141416"
  surface-raised: "#191A1D"
  text: "#F0F0F1"
  muted: "#8B8E95"
  border: "#292A2E"
  primary: "#D6D7DA"
  alert: "#B67C80"
  warning: "#AA956D"
  success: "#819B8D"
  focus: "#F0F0F1"
  bright-canvas: "#EBECEF"
  bright-sidebar: "#E3E4E7"
  bright-surface: "#F7F7F8"
  bright-text: "#17181A"
  bright-border: "#D1D3D8"
typography:
  body:
    fontFamily: "Segoe UI, Aptos, Helvetica Neue, Arial, sans-serif"
  mono:
    fontFamily: "Cascadia Mono, IBM Plex Mono, Consolas, monospace"
rounded:
  DEFAULT: "0.3125rem"
  sm: "0.25rem"
  md: "0.375rem"
spacing:
  unit: "0.5rem"
  section-gap: "0.75rem"
  page-max: "91.25rem"
components:
  button: {}
  upload: {}
  chart: {}
  table: {}
  status: {}
---

# KAIROS Design System

## Overview

### Creative North Star

KAIROS is an air-gapped operations console: compact, quiet, and built to be read under pressure. Its layout borrows the reference dashboard’s narrow rail, dense status cards, and ranked work surface, while replacing bright SaaS color with matte black, graphite, and measured typographic contrast.

### Product context and register

- **Audience and primary job:** SOC analysts and SIH judges upload traffic, inspect future risk, verify evidence, and understand model limits.
- **Usage scene:** Laptop and projected offline demonstrations with medium-to-high information density.
- **Register:** Mixed. The public landing route is expressive and directional; the dashboard remains a compact operational tool.
- **Memorable signature:** A matte network-to-forecast field introduces the 10/30/60-second concept, then resolves into the dashboard's flight-recorder instrument.
- **Restraint:** No neon, glow, glass, gradients, decorative terminal texture, invented performance claims, or decorative dashboard clutter.
- **Token ownership/runtime mapping:** This file owns visual intent and exact tokens. `react-ui/src/styles.css` is the runtime CSS-variable adapter. Recharts uses the same literal chart-safe equivalents because SVG presentation values do not resolve reliably through every rendering path.

## Colors

The workspace uses five neutral depths: black canvas, black sidebar, graphite surface, raised graphite, and steel borders. Off-white is reserved for primary text and committed actions. Muted red, amber, and green appear only for risk, caution, and healthy state; none are fluorescent and every state also has text or icon semantics.

Dark mode is the matte operational default. Bright mode uses warm white and pale graphite rather than pure white, while retaining the same semantic red, amber, and green roles. The first visit follows the operating-system preference; an explicit user choice is persisted locally.

## Typography

A reliable offline system-sans stack carries navigation and prose at a 16px body baseline. The landing route adds the locally available Bahnschrift SemiCondensed/Arial Narrow stack for large campaign statements without a web-font request. Operational labels remain at least 12px-equivalent, while risk values and section headings use decisive size and weight. The mono stack is restricted to probabilities, timestamps, model artifacts, ranks, and network values. Headings remain sentence case.

## Layout

The root route is a full-height landing surface with a concise proposition, one animated network-to-forecast field, three grounded capabilities, the processing method, and deliberate entry into the product. `#dashboard` uses an inset, rounded application frame with a compact top command bar. Its primary surface is one forecast workbench: a narrow traffic-input column beside a large 10/30/60-second probability instrument. Forecast status and quality sit directly above the plot; stage coverage, analyst context, and ranked evidence follow only after an analysis runs. Optional live capture stays collapsed until requested. Both surfaces reflow without horizontal page overflow.

## Elevation & Depth

Depth comes only from adjacent matte tones and one-pixel borders. Shadows, blur, shine, and glow are prohibited. Raised states become one neutral step lighter.

## Shapes

Panels use 6px radii and controls use 4–5px radii. Status labels are compact rounded rectangles, not decorative pills. Timeline nodes are square to reinforce the instrument-panel character.

## Components

### Navigation

The active destination uses a graphite fill and steel border, never a saturated brand block. Icons are subordinate grey linework. The local-engine card stays visible at the foot of the rail.

### Buttons and actions

The single primary action is off-white with near-black text. Secondary actions are graphite outlines. Hover changes one surface step; focus uses a clear two-pixel off-white ring. Busy and disabled states preserve geometry.

### Upload and feedback

The upload zone is a quiet dashed instrument bay with a keyboard-accessible picker. Selected files, errors, cancellation, and the 750 MiB limit remain explicit. Errors use a muted red edge and dark red-brown surface rather than a bright banner.

### Forecast and evidence

Validated 10/30/60-second risk remains primary. The immediate GNN-Transformer output stays inside a diagnostic disclosure. The chart uses a pale grey signal and muted red threshold. Tables, stage coverage, input quality, and packet evidence retain text labels so color is never the only carrier.

### Motion

The landing page concentrates motion in one authored threat field: staged hero entrance, forecast-path draw, packet travel, a bounded scan, subtle node pulse, pointer tilt, and a View Transition into the dashboard. Product motion stays limited to the result reveal, chart update, and busy indicator. Reduced-motion mode hides travelling packets, resolves the path immediately, removes spatial transforms, and preserves state feedback.

## Do's and Don'ts

- **Do:** Make the interface feel like a serious offline instrument.
- **Do:** Use density, alignment, and typography for hierarchy.
- **Do:** Keep forecast caveats beside the values they qualify.
- **Don't:** Add purple, electric blue, acid green, glow, glass, gradients, or cyberpunk ornament.
- **Don't:** Turn the dashboard into a marketing page or hide unsupported stages.
- **Don't:** imply SHAP contribution proves causality or that a forecast confirms an attack.