import React from 'react';

const LABELS = {
  NONE: 'No mapped stage',
  RECONNAISSANCE: 'Reconnaissance',
  INITIAL_ACCESS: 'Initial access',
  LATERAL_MOVEMENT: 'Lateral movement',
  COMMAND_AND_CONTROL: 'Command & control',
  EXFILTRATION: 'Exfiltration',
  IMPACT: 'Impact',
};

function label(stage) {
  return LABELS[stage] || stage?.replaceAll('_', ' ') || 'Unknown';
}

function StageAnnotations({ prediction }) {
  const horizons = prediction?.validatedForecast?.horizons || [];
  const coverage = prediction?.stageCoverage || {};
  const evidence = prediction?.inputProjectionDetail;

  return (
    <section className="panel stage-panel" aria-labelledby="stage-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Validated conditional stage outlook</p>
          <h2 id="stage-title">Stage coverage</h2>
        </div>
      </div>
      <ol className="stage-track">
        {horizons.map((item) => (
          <li key={item.horizonSeconds}>
            <span className="stage-step">{Math.round(item.horizonSeconds)}s</span>
            <strong>{label(item.predictedStageIfAttack)}</strong>
          </li>
        ))}
      </ol>
      <dl className="coverage-list">
        <div>
          <dt>Supported by training</dt>
          <dd>{(coverage.supported || []).map(label).join(', ') || 'Not reported'}</dd>
        </div>
        <div>
          <dt>Not supported</dt>
          <dd>{(coverage.unsupported || []).map(label).join(', ') || 'Not reported'}</dd>
        </div>
      </dl>
      <p className="panel-note">{coverage.policy || 'Stage labels require analyst verification.'}</p>
      {evidence && (
        <p className="packet-evidence-note">
          Packet evidence retained · {evidence.windows?.length || 0} windows · {evidence.preserved_empty_windows || 0} empty windows preserved.
        </p>
      )}
    </section>
  );
}

export default StageAnnotations;
