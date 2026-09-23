import React, { useEffect, useRef, useState } from 'react';
import FlaggedFlowsTable from './components/FlaggedFlowsTable';
import LiveDashboard from './components/LiveDashboard';
import NarrativePanel from './components/NarrativePanel';
import ProbabilityTimeline from './components/ProbabilityTimeline';
import QualityBadge from './components/QualityBadge';
import StageAnnotations from './components/StageAnnotations';
import { explainApiError, forecastTraffic } from './api/client';
import './styles.css';

const MAX_FILE_BYTES = 750 * 1024 * 1024;

const Icon = ({ name, size = 19 }) => {
  const paths = {
    overview: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    upload: <><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M4 15v5h16v-5" /></>,
    forecast: <><path d="M3 18 9 12l4 3 8-9" /><path d="M17 6h4v4" /></>,
    live: <><path d="M4.9 19.1a10 10 0 0 1 0-14.2" /><path d="M8.5 15.5a5 5 0 0 1 0-7" /><circle cx="12" cy="12" r="1.5" /><path d="M15.5 8.5a5 5 0 0 1 0 7" /><path d="M19.1 4.9a10 10 0 0 1 0 14.2" /></>,
    shield: <><path d="M12 3 4.5 6v5.5c0 4.7 3.1 7.8 7.5 9.5 4.4-1.7 7.5-4.8 7.5-9.5V6L12 3Z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    pulse: <path d="M3 12h4l2-5 4 10 2-5h6" />,
    file: <><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v5h5" /><path d="M9 13h6M9 17h6" /></>,
    arrow: <><path d="M5 12h14" /><path d="m14 7 5 5-5 5" /></>,
  };
  return <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
};

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
}

function validateFile(file) {
  if (!file) return 'Choose a CICFlowMeter CSV or packet capture to continue.';
  const lowerName = file.name.toLowerCase();
  if (!['.csv', '.pcap', '.pcapng'].some((suffix) => lowerName.endsWith(suffix))) return 'Use a CICFlowMeter .csv or a .pcap/.pcapng packet capture.';
  if (file.size === 0) return 'The selected file is empty.';
  if (file.size > MAX_FILE_BYTES) return 'The selected file exceeds the 750 MiB limit.';
  return '';
}

function App() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const abortRef = useRef(null);
  const resultRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    document.title = 'Security overview — KAIROS';
    return () => abortRef.current?.abort();
  }, []);

  const chooseFile = (candidate) => {
    const validation = validateFile(candidate);
    setFile(candidate || null);
    setError(validation);
  };

  const runForecast = async (candidate = file) => {
    const validation = validateFile(candidate);
    if (validation) { setError(validation); return; }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setError('');
    try {
      const response = await forecastTraffic(candidate, 5, controller.signal);
      setResult(response);
      window.requestAnimationFrame(() => resultRef.current?.focus());
    } catch (requestError) {
      setError(explainApiError(requestError));
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setBusy(false);
      }
    }
  };

  const loadSample = async () => {
    setBusy(true);
    setError('');
    try {
      const response = await fetch('/sample-attack.csv');
      if (!response.ok) throw new Error('sample unavailable');
      const blob = await response.blob();
      const sample = new File([blob], 'kairos-sample-attack.csv', { type: 'text/csv' });
      setFile(sample);
      await runForecast(sample);
    } catch (sampleError) {
      setError('The bundled sample could not be loaded. Refresh the dashboard and try again.');
      setBusy(false);
    }
  };

  const prediction = result?.prediction;
  const primaryForecast = prediction?.validatedForecast?.primary;
  const highRisk = Boolean(primaryForecast?.alert);
  const forecastAvailable = Boolean(prediction?.validatedForecast?.available);
  const riskValue = forecastAvailable ? `${((primaryForecast?.probability || 0) * 100).toFixed(1)}%` : '—';
  const quality = prediction?.quality || 'awaiting input';
  const scrollToUpload = () => document.getElementById('traffic-input')?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <a className="brand-lockup" href="#overview" aria-label="KAIROS security overview">
          <span className="brand-mark"><span /><span /><span /></span>
          <span><strong>KAIROS</strong><small>Threat foresight</small></span>
        </a>
        <nav className="primary-nav" aria-label="Dashboard sections">
          <p>Workspace</p>
          <a className="active" href="#overview"><Icon name="overview" />Overview</a>
          <a href="#traffic-input"><Icon name="upload" />Traffic analysis</a>
          <a href="#forecast-results"><Icon name="forecast" />Forecast results</a>
          <a href="#live-capture"><Icon name="live" />Live capture</a>
        </nav>
        <div className="sidebar-status">
          <span className="status-orbit"><Icon name="shield" size={22} /></span>
          <div><strong>Local engine</strong><span><i /> Offline ready</span></div>
          <p>Traffic stays inside your KAIROS deployment.</p>
        </div>
        <p className="sidebar-version">SIH 26153 · research build</p>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb"><span>Dashboard</span><b>/</b><strong>Security overview</strong></div>
          <div className="topbar-meta"><span className="topbar-dot" />Core services expected on localhost</div>
        </header>

        <main>
          <section className="page-heading" id="overview" aria-labelledby="page-title">
            <div>
              <p className="eyebrow">Predictive network defence</p>
              <h1 id="page-title">Security overview</h1>
              <p>Forecast attacker progression from ordered network states—not just what is happening now.</p>
            </div>
            <div className="heading-actions">
              <button className="button secondary" type="button" onClick={loadSample} disabled={busy}>Use sample</button>
              <button className="button primary" type="button" onClick={scrollToUpload}><Icon name="upload" size={17} />Analyze traffic</button>
            </div>
          </section>

          <section className="metric-grid" aria-label="Forecast summary">
            <article className={`metric-card ${highRisk ? 'metric-danger' : 'metric-primary'}`}>
              <span className="metric-icon"><Icon name="forecast" /></span>
              <div><p>Validated 60s risk</p><strong>{riskValue}</strong><small>{forecastAvailable ? (highRisk ? 'Threshold crossed' : 'Below calibrated threshold') : 'Run an analysis'}</small></div>
            </article>
            <article className="metric-card metric-teal"><span className="metric-icon"><Icon name="clock" /></span><div><p>Forecast horizons</p><strong>10 · 30 · 60s</strong><small>Three future checkpoints</small></div></article>
            <article className="metric-card metric-amber"><span className="metric-icon"><Icon name="pulse" /></span><div><p>Input quality</p><strong>{quality.replaceAll('_', ' ')}</strong><small>{prediction?.qualityDetail ? 'Distribution guard evaluated' : 'Waiting for evidence'}</small></div></article>
            <article className="metric-card metric-slate"><span className="metric-icon"><Icon name="shield" /></span><div><p>Operating mode</p><strong>Offline first</strong><small>Analyst verification required</small></div></article>
          </section>

          <section className="intake-grid" id="traffic-input" aria-label="Traffic analysis input">
            <form className="panel upload-panel" noValidate onSubmit={(event) => { event.preventDefault(); runForecast(); }}>
              <div className="panel-heading">
                <div><p className="eyebrow">Traffic analysis</p><h2>Upload network evidence</h2></div>
                <span className="format-badge">CSV · PCAP · PCAPNG</span>
              </div>
              <p className="section-intro">Analyze CICFlowMeter data or a packet capture through the local native, Java, and Python pipeline.</p>
              <div className={dragOver ? 'drop-zone drag-over' : 'drop-zone'} role="button" tabIndex={0} aria-label="Choose a traffic file"
                onClick={() => fileInputRef.current?.click()}
                onKeyDown={(event) => { if ((event.key === 'Enter' || event.key === ' ') && !event.isComposing) fileInputRef.current?.click(); }}
                onDragOver={(event) => { event.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(event) => { event.preventDefault(); setDragOver(false); chooseFile(event.dataTransfer.files?.[0]); }}>
                <input ref={fileInputRef} type="file" accept=".csv,.pcap,.pcapng,text/csv,application/vnd.tcpdump.pcap" onChange={(event) => chooseFile(event.target.files?.[0])} disabled={busy} />
                <span className="upload-glyph"><Icon name="upload" size={24} /></span>
                <strong>{file ? 'Choose a different file' : 'Drop traffic evidence here'}</strong>
                <span>or click to browse · maximum 750 MiB</span>
              </div>

              {file && <div className="file-row"><div><span className="file-type"><Icon name="file" size={18} /></span><div><strong>{file.name}</strong><span>{formatBytes(file.size)} · ready for local analysis</span></div></div><button type="button" className="text-button" onClick={() => { setFile(null); setError(''); }} disabled={busy}>Remove</button></div>}
              {error && <div className="inline-alert" role="alert"><strong>Analysis needs attention</strong><span>{error}</span></div>}
              <div className="upload-actions">
                <button type="submit" className="button primary" disabled={!file || busy} aria-busy={busy}>{busy ? <><span className="busy-dot" />Analysing traffic</> : <><Icon name="forecast" size={17} />Run validated forecast</>}</button>
                {busy ? <button type="button" className="button secondary" onClick={() => abortRef.current?.abort()}>Cancel</button> : <button type="button" className="button secondary" onClick={loadSample}>Load sample attack</button>}
              </div>
              <p className="privacy-note"><Icon name="shield" size={15} />Your file is sent only to the local KAIROS engine.</p>
            </form>

            <aside className="panel route-panel" aria-labelledby="route-title">
              <div className="panel-heading"><div><p className="eyebrow">Verified model route</p><h2 id="route-title">From flow to foresight</h2></div><span className="verified-mark"><Icon name="shield" size={17} />Verified</span></div>
              <ol className="route-list">
                <li><span>01</span><div><strong>Window traffic</strong><p>Preserve ordered 10-second network states.</p></div></li>
                <li><span>02</span><div><strong>Encode graph context</strong><p>Capture host-flow structure and packet evidence.</p></div></li>
                <li><span>03</span><div><strong>Forecast future risk</strong><p>Score validated 10, 30, and 60-second horizons.</p></div></li>
                <li><span>04</span><div><strong>Explain the warning</strong><p>Rank SHAP evidence and map supported stages.</p></div></li>
              </ol>
              <div className="model-note"><span>Core distinction</span><strong>Future-state forecasting</strong><p>The immediate GNN-Transformer output remains a diagnostic, not the primary risk label.</p></div>
            </aside>
          </section>

          <section id="forecast-results">
            {result ? (
              <div className="results" aria-labelledby="result-title">
                <div className={`result-ribbon ${highRisk ? 'result-high' : ''}`} ref={resultRef} tabIndex="-1">
                  <div className="result-status-icon"><Icon name={highRisk ? 'pulse' : 'shield'} size={23} /></div>
                  <div className="result-copy"><p className="eyebrow">Latest inference · {result.artifactVersion}</p><h2 id="result-title">{!forecastAvailable ? 'Validated forecast unavailable' : highRisk ? 'Escalation threshold crossed' : 'Below calibrated threshold'}</h2></div>
                  <div className="risk-stamp"><span>Validated 60-second risk</span><strong>{riskValue}</strong></div>
                  <dl className="result-facts"><div><dt>Conditional stage</dt><dd>{(primaryForecast?.predictedStageIfAttack || 'unknown').replaceAll('_', ' ')}</dd></div><div><dt>Threshold</dt><dd>{forecastAvailable ? `${((primaryForecast?.threshold || 0) * 100).toFixed(1)}%` : 'N/A'}</dd></div><div><dt>Inference</dt><dd>{Math.round(prediction?.latencyMs || 0)} ms</dd></div></dl>
                </div>
                <div className={`quality-callout quality-${prediction?.quality || 'ok'}`} role="status"><QualityBadge quality={prediction?.quality} detail={prediction?.qualityDetail} /><p>{prediction?.quality === 'ok' ? 'Input distribution is within the configured quality guard; analyst verification still applies.' : 'Input quality is outside the trusted training range. Treat every forecast as advisory and verify against packet evidence.'}</p></div>
                <div className="result-grid"><ProbabilityTimeline prediction={prediction} /><StageAnnotations prediction={prediction} /><NarrativePanel narrative={result.narrative} /><FlaggedFlowsTable features={prediction?.topFeatures || []} /></div>
              </div>
            ) : (
              <div className="panel empty-workbench" aria-label="No forecast yet">
                <span className="empty-icon"><Icon name="forecast" size={25} /></span>
                <div><p className="eyebrow">Forecast workspace</p><strong>No analysis has run yet</strong><p>Upload evidence or use the sample to reveal future risk, stage coverage, and ranked forecast drivers.</p></div>
                <button type="button" className="text-action" onClick={scrollToUpload}>Go to upload <Icon name="arrow" size={16} /></button>
              </div>
            )}
          </section>

          <LiveDashboard />
        </main>
        <footer><span>KAIROS · Network Attack World Model</span><span>Explainable · offline-first · analyst verified</span></footer>
      </div>
    </div>
  );
}

export default App;
