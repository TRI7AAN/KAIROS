import React from 'react';

function NarrativePanel({ narrative }) {
  const online = narrative?.mode === 'gemini-online';
  const fallback = narrative?.mode === 'offline-local-fallback';

  return (
    <section className="panel narrative-panel" aria-labelledby="briefing-title">
      <div className="panel-heading">
        <div>
          <h2 id="briefing-title">What warrants attention</h2>
          <p className="panel-subtitle">Analyst briefing</p>
        </div>
        <span className={online ? 'mode-badge online' : 'mode-badge offline'}>
          <span aria-hidden="true">{online ? '↗' : '●'}</span>
          {online ? 'Gemini online' : fallback ? 'Local fallback' : 'Local · offline'}
        </span>
      </div>
      <blockquote>{narrative?.text || 'No narrative was returned.'}</blockquote>
      <div className="verification-line">
        <span aria-hidden="true">◇</span>
        <span>Decision support only. Verify against packet evidence and local policy.</span>
      </div>
    </section>
  );
}

export default NarrativePanel;
