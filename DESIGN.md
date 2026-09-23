---
version: alpha
name: "KAIROS"
description: "An operational command dashboard for explainable network-attack forecasting."
colors:
  navy: "#172238"
  navy-soft: "#23314D"
  canvas: "#F3F6FB"
  surface: "#FFFFFF"
  text: "#26334D"
  muted: "#73809A"
  border: "#E3E9F2"
  primary: "#536DFE"
  teal: "#16A99A"
  alert: "#E45B65"
  warning: "#E99B2F"
  success: "#1D9B6C"
  focus: "#7158E2"
typography:
  body:
    fontFamily: "Segoe UI, Aptos, Helvetica Neue, Arial, sans-serif"
  mono:
    fontFamily: "Cascadia Mono, IBM Plex Mono, Consolas, monospace"
rounded:
  DEFAULT: "0.375rem"
  sm: "0.3125rem"
  md: "0.5rem"
  lg: "0.625rem"
spacing:
  unit: "0.5rem"
  section-gap: "1.25rem"
  page-max: "88.75rem"
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

KAIROS should feel like an incident commander’s operational console: measured, legible, calm under pressure, and evidence-first. Its information hierarchy borrows the proven sidebar, summary-card, chart, and table rhythm of DashboardKit while remaining unmistakably a predictive-security product rather than a reskinned sales dashboard.

### Product context and register

- **Audience and primary job:** SOC analysts and SIH judges need to upload traffic, understand a future-risk forecast, inspect evidence, and distinguish measured facts from model projections.
- **Target market(s) and evidence:** India’s critical-information-infrastructure context, established by the SIH problem statement and repository architecture.
- **Locale(s) and language policy:** English UI; technical identifiers remain in their source schema.
- **Usage scene:** Laptop or projected demo, often offline, with urgent interpretation and medium data density.
- **Register:** Product dashboard.
- **Memorable signature:** The horizon instrument makes the calibrated 10/30/60-second future-risk trajectory visually dominant and keeps the current GNN-Transformer score in a subordinate diagnostic disclosure.
- **Restraint:** Upload, errors, evidence tables, and narrative reading use conventional controls and stable layouts.
- **Anti-references:** Avoid generic neon “hacker” dashboards, glassmorphism, decorative terminal noise, and unearned claims of causality.
- **Token ownership/runtime mapping:** This file owns visual intent and exact tokens; `react-ui/src/styles.css` is the runtime CSS-variable adapter.

## Colors

The navy sidebar anchors the workspace; a cool canvas and white surfaces keep dense evidence readable. Indigo is reserved for forecast/action emphasis, teal for verified/local state, coral for elevated risk, and amber for caution. Focus always uses violet and never relies on color alone. Charts repeat labels and markers so stage and threshold meaning are not color-only.

## Typography

The UI uses a restrained system sans stack for reliable offline rendering and a compact dashboard cadence. Numeric values and model artifacts use the mono stack with tabular figures. Utility labels are tracked uppercase; headings use sentence case.

## Layout

The desktop layout uses a persistent 250px navigation sidebar and an 88.75rem centered workspace. Dashboard summaries use a four-card row; upload and model route use an asymmetric 2/3–1/3 grid. Below 56rem the sidebar becomes a compact top navigation and all analytical panels reflow to one column. The page scrolls naturally, while tables own horizontal overflow with a stable scrollbar gutter.

## Elevation & Depth

Hierarchy comes from white surfaces, cool borders, and one restrained low-opacity shadow token. Nested content is flat. No blur, translucent glass, neon glow, or decorative terminal texture is used.

## Shapes

Panels use 8px radii and controls use 5–6px radii. Pills are reserved for status and compact metadata, not general containers.

## Components

### Foundational visual states

Interactive controls define hover, focus-visible, pressed, disabled, and busy states. Loading is a stable inline instrument pulse with text. Errors remain persistent beside the upload workflow with a retry path. Reduced-motion mode removes transforms and pulses.

### Buttons and actions

The solid indigo button is the sole primary action in its area. The sample action is outline-neutral. Busy actions keep their dimensions and expose `aria-busy`. Disabled controls use both reduced contrast and disabled semantics.

### Navigation and data display

The app has one dashboard route with in-page landmark navigation. Desktop navigation is persistent; narrow navigation scrolls horizontally without hiding destinations. Tables use native semantics, horizontal scrolling, stable headers, and an explicit empty state. Forecast stages appear in ordered windows.

### Forms and overlays

The upload form owns validation with `noValidate`. A native file input is activated by a visible drop target and supports keyboard selection. File type, size, errors, and removal are explicit. No browser alert, confirm, or prompt is used.

### Iconography

Small inline SVG marks use a consistent 1.8px stroke. Icons supplement visible labels; they never replace them for primary actions.

### Motion

One 420ms page reveal and a 180ms control response provide continuity. Busy instrumentation may pulse. Reduced motion disables transforms, staggers, and continuous animation.

### Content and data visualization

Copy is factual and calm: “forecast,” “evidence,” and “requires analyst verification.” Probabilities show one decimal percent; latency shows whole milliseconds. The chart labels the alert threshold and simulated horizons. The evidence table names SHAP contributions and never calls them causal.

## Do's and Don'ts

- **Do:** Separate observed inputs, model forecasts, and analyst interpretation.
- **Do:** Keep offline/local mode visible wherever narrative provenance matters.
- **Don't:** Use cybersecurity decoration that competes with evidence.
- **Don't:** imply a SHAP contribution proves causality or a forecast confirms an attack.
