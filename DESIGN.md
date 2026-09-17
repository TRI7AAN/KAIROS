---
version: alpha
name: "KAIROS"
description: "An air-gapped incident dossier for explainable network-attack forecasting."
colors:
  ink: "#10243E"
  ink-muted: "#52647A"
  paper: "#F4F3ED"
  surface: "#FFFEF8"
  grid: "#CFD4D6"
  lapis: "#2459D3"
  alert: "#C43D2B"
  warning: "#B66A16"
  success: "#28735A"
  focus: "#6B4EFF"
typography:
  display:
    fontFamily: "Georgia, Cambria, Times New Roman, serif"
  body:
    fontFamily: "Aptos, Segoe UI, Helvetica Neue, Arial, sans-serif"
  utility:
    fontFamily: "Arial Narrow, Roboto Condensed, Aptos Narrow, sans-serif"
  mono:
    fontFamily: "Cascadia Mono, IBM Plex Mono, Consolas, monospace"
rounded:
  DEFAULT: "0.375rem"
  sm: "0.25rem"
  md: "0.375rem"
  lg: "0.75rem"
spacing:
  unit: "0.5rem"
  section-gap: "1.25rem"
  page-max: "90rem"
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

KAIROS should feel like an incident commander’s printed intelligence dossier laid over a live network plotting table: measured, legible, and evidence-first. It is a product surface, not a marketing site.

### Product context and register

- **Audience and primary job:** SOC analysts and SIH judges need to upload traffic, understand a future-risk forecast, inspect evidence, and distinguish measured facts from model projections.
- **Target market(s) and evidence:** India’s critical-information-infrastructure context, established by the SIH problem statement and repository architecture.
- **Locale(s) and language policy:** English UI; technical identifiers remain in their source schema.
- **Usage scene:** Laptop or projected demo, often offline, with urgent interpretation and medium data density.
- **Register:** Product dashboard.
- **Memorable signature:** The forecast tape separates the current score from numbered future windows and overlays the predicted MITRE-stage sequence.
- **Restraint:** Upload, errors, evidence tables, and narrative reading use conventional controls and stable layouts.
- **Anti-references:** Avoid generic neon “hacker” dashboards, glassmorphism, decorative terminal noise, and unearned claims of causality.
- **Token ownership/runtime mapping:** This file owns visual intent and exact tokens; `react-ui/src/styles.css` is the runtime CSS-variable adapter.

## Colors

Paper and surface tokens create the dossier canvas. Ink carries structure; lapis is the model forecast; alert and warning are reserved for risk semantics; success identifies verified local/offline operation. Focus always uses the violet focus token and never relies on color alone. Charts repeat labels and markers so stage and threshold meaning are not color-only.

## Typography

Georgia is reserved for the product name and decisive result language. The body stack optimizes operational reading. Utility labels use a narrow system stack with tracked uppercase; numeric values and model artifacts use the mono stack with tabular figures. Headings use sentence case.

## Layout

The desktop layout uses a 90rem centered canvas, a compact masthead, and an asymmetric 5/7 workbench grid. Result panels reflow to one column below 62rem; upload actions stack below 42rem. The page scrolls naturally, while tables own horizontal overflow with a stable scrollbar gutter. Result geometry remains reserved during requests.

## Elevation & Depth

Hierarchy comes from paper tones, rules, and offset ink shadows. Static panels use one restrained two-pixel offset; nested content is flat. No blur or translucent glass is used.

## Shapes

Panels and controls use tight radii. The forecast plot may use a larger radius as the singular live instrument. Pills are reserved for status and MITRE stages, not general containers.

## Components

### Foundational visual states

Interactive controls define hover, focus-visible, pressed, disabled, and busy states. Loading is a stable inline instrument pulse with text. Errors remain persistent beside the upload workflow with a retry path. Reduced-motion mode removes transforms and pulses.

### Buttons and actions

The solid ink button is the sole primary action in its area. The sample action is outline-neutral. Busy actions keep their dimensions and expose `aria-busy`. Disabled controls use both reduced contrast and disabled semantics.

### Navigation and data display

The app has one dashboard route and no decorative navigation. Tables use native semantics, horizontal scrolling, stable headers, and an explicit empty state. Forecast stages appear in ordered windows.

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
