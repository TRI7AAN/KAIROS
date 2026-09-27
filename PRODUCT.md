# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Primary:** SOC analysts reviewing network telemetry and deciding whether a forecast warrants investigation.
- **Evaluation:** SIH judges assessing whether the prototype satisfies Problem Statement 26153.
- These roles are inferred from the supplied SIH brief, repository documentation, and current dashboard copy.

## Product Purpose

KAIROS ingests CSV flow records or PCAP/PCAPNG traffic, models ordered network states, and presents future attack-risk horizons, supported attack stages, and interpretable evidence. Success means an analyst can distinguish observed traffic, calibrated forecasts, model diagnostics, and known limitations without needing a cloud service.

## Positioning

KAIROS is an offline-first predictive defence prototype that combines packet and flow evidence with graph-temporal modelling. It explicitly separates the calibrated temporal forecast from the GNN-Transformer transition diagnostic instead of presenting a current-state classifier as a future-risk score.

## Operating Context

- Laptop and projected SIH demonstrations, often without internet access.
- Analysts upload evidence, run a forecast, inspect 10/30/60-second risk, review stage coverage and SHAP-ranked drivers, and optionally observe passive live capture.
- The interface must remain usable with dense evidence, long identifiers, server errors, and narrow screens.

## Capabilities and Constraints

- Accept CICFlowMeter CSV and PCAP/PCAPNG uploads up to 750 MiB.
- Preserve the existing validated forecast, quality-warning, stage-coverage, narrative, evidence-table, and passive live-capture behavior.
- Offline operation is the default; any optional online narrative mode must never be required for core forecasting.
- Forecasts are advisory and require analyst verification.
- Three SIH-named attack stages currently have no learned support and must remain visibly disclosed rather than fabricated.

## Brand Commitments

- Product name: KAIROS.
- Voice: factual, calm, operational, and evidence-first.
- User-approved visual reference: a compact dark command dashboard, reinterpreted without neon color.
- User-approved palette direction: matte black and graphite grey; semantic color appears only where risk or status requires it.

## Evidence on Hand

- SIH Problem Statement 26153 supplied by the user.
- Reproducible benchmark artifacts under `results/`.
- Architecture, limitations, and operating instructions in `README.md` and `docs/`.
- No customer logos, testimonials, or production-deployment claims are available and none may be invented.

## Product Principles

1. Future risk is visually primary; immediate model scores remain diagnostic.
2. Evidence and limitations are always visible close to the forecast they qualify.
3. Offline operation and local data handling remain explicit.
4. Dense information must stay calm, legible, and fast to scan.
5. Semantic status never depends on color alone.

## Accessibility & Inclusion

Target WCAG 2.2 AA with keyboard-operable upload and live controls, visible focus, reduced-motion support, semantic tables, and responsive reflow.
