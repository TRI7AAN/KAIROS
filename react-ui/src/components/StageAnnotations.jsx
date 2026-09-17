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

function StageAnnotations({ prediction }) {
  const predicted = prediction?.predictedStage || 'NONE';
  const stages = prediction?.rollout?.predictedStages || [];

  return (
    <section className="panel stage-panel" aria-labelledby="stage-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">MITRE-aligned progression</p>
          <h2 id="stage-title">Stage outlook</h2>
        </div>
      </div>
      <ol className="stage-track">
        <li>
          <span className="stage-step">Now</span>
          <strong>{LABELS[predicted] || predicted}</strong>
        </li>
        {stages.map((stage, index) => (
          <li key={`${stage}-${index}`}>
            <span className="stage-step">T+{index + 1}</span>
            <strong>{LABELS[stage] || stage}</strong>
          </li>
        ))}
      </ol>
      <p className="panel-note">Stage labels are model classifications and require analyst verification.</p>
    </section>
  );
}

export default StageAnnotations;
