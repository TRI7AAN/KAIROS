import React, { useEffect, useRef, useState } from 'react';
import FlaggedFlowsTable from './components/FlaggedFlowsTable';
import LandingPage from './components/LandingPage';
import LiveDashboard from './components/LiveDashboard';
import NarrativePanel from './components/NarrativePanel';
import ProbabilityTimeline from './components/ProbabilityTimeline';
import QualityBadge from './components/QualityBadge';
import StageAnnotations from './components/StageAnnotations';
import { explainApiError, forecastTraffic } from './api/client';
import './styles.css';
import './landing.css';

const MAX_FILE_BYTES = 750 * 1024 * 1024;

const Icon = ({ name, size = 19 }) => {
  const paths = {
    upload: <><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M4 15v5h16v-5" /></>,
    forecast: <><path d="M3 18 9 12l4 3 8-9" /><path d="M17 6h4v4" /></>,
    shield: <><path d="M12 3 4.5 6v5.5c0 4.7 3.1 7.8 7.5 9.5 4.4-1.7 7.5-4.8 7.5-9.5V6L12 3Z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></>,
    pulse: <path d="M3 12h4l2-5 4 10 2-5h6" />,
    file: <><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v5h5" /><path d="M9 13h6M9 17h6" /></>,
    sun: <><circle cx="12" cy="12" r="3.5" /><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.65 17.65l1.42 1.42M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.65 6.35l1.42-1.42" /></>,
    moon: <path d="M20.5 15.2A8.4 8.4 0 0 1 8.8 3.5 8.5 8.5 0 1 0 20.5 15.2Z" />,
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

function getInitialTheme() {
  try {
    const savedTheme = window.localStorage.getItem('kairos-theme');
    if (savedTheme === 'dark' || savedTheme === 'light') return savedTheme;
  } catch {
    // Storage can be unavailable in privacy-restricted browser sessions.
  }
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function Dashboard() {
  const [theme, setTheme] = useState(getInitialTheme);
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const abortRef = useRef(null);
  const resultRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    document.title = 'Attack forecast — KAIROS';
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#0B0B0C' : '#EBECEF');
    try {
      window.localStorage.setItem('kairos-theme', theme);
    } catch {
      // The selected theme still applies for this session.
    }
  }, [theme]);

  const chooseFile = (candidate) => {
    const validation = validateFile(candidate);
    setFile(candidate || null);
    setError(validation);
  };

  const runForecast = async (candidate = file) => {
    const validation = validateFile(candidate);
    if (validation) {
      setError(validation);
      return;
    }

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
    } catch {
      setError('The bundled sample could not be loaded. Refresh the dashboard and try again.');
      setBusy(false);
    }
  };

  const prediction = result?.prediction;
  const primaryForecast = prediction?.validatedForecast?.primary;
  const forecastAvailable = Boolean(prediction?.validatedForecast?.available);
  const highRisk = Boolean(primaryForecast?.alert);
  const riskValue = forecastAvailable ? `${((primaryForecast?.probability || 0) * 100).toFixed(1)}%` : '—';
  const thresholdValue = forecastAvailable ? `${((primaryForecast?.threshold || 0) * 100).toFixed(1)}%` : '—';
  const stageValue = (primaryForecast?.predictedStageIfAttack || 'unknown').replaceAll('_', ' ');

  return (
    <div className="app-shell">
      <header className="app-bar">
        <a className="brand-lockup" href="#home" aria-label="Return to KAIROS home">
          <span className="brand-mark"><span /><span /><span /></span>
          <span><strong>KAIROS</strong></span>
        </a>

        <nav className="primary-nav" aria-label="Dashboard sections">
          <a className="active" href="#forecast-workspace">Forecast</a>
          <a href="#forecast-results">Evidence</a>
          <a href="#live-capture">Live capture</a>
        </nav>

        <div className="app-actions">
          <span className="engine-state"><i />Local engine ready</span>
          <button
            className="theme-toggle"
            type="button"
            onClick={() => setTheme((currentTheme) => currentTheme === 'dark' ? 'light' : 'dark')}
            aria-label={`Switch to ${theme === 'dark' ? 'bright' : 'dark'} mode`}
            title={`Switch to ${theme === 'dark' ? 'bright' : 'dark'} mode`}
          >
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={17} />
            <span>{theme === 'dark' ? 'Bright' : 'Dark'}</span>
          </button>
        </div>
      </header>

      <main className="dashboard">
        <header className="workspace-heading">
          <div>
            <h1>Threat forecast</h1>
            <p>Analyze traffic. Review future risk. Validate the evidence.</p>
          </div>
          <span className="advisory-note"><Icon name="shield" size={16} />Verify before escalation</span>
        </header>

        <section className="forecast-workspace" id="forecast-workspace" aria-label="Forecast workspace">
          <form className="panel analysis-input" noValidate onSubmit={(event) => { event.preventDefault(); runForecast(); }}>
            <div className="panel-heading">
              <div>
                <h2>Traffic input</h2>
                <p>CSV / PCAP / PCAPNG · 750 MiB max</p>
              </div>
            </div>

            <div
              className={dragOver ? 'drop-zone drag-over' : 'drop-zone'}
              role="button"
              tabIndex={0}
              aria-label="Choose a traffic file"
              onClick={() => fileInputRef.current?.click()}
              onKeyDown={(event) => {
                if ((event.key === 'Enter' || event.key === ' ') && !event.isComposing) fileInputRef.current?.click();
              }}
              onDragOver={(event) => {
                event.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragOver(false);
                chooseFile(event.dataTransfer.files?.[0]);
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.pcap,.pcapng,text/csv,application/vnd.tcpdump.pcap"
                onChange={(event) => chooseFile(event.target.files?.[0])}
                disabled={busy}
              />
              <span className="upload-glyph"><Icon name="upload" size={22} /></span>
              <strong>{file ? 'Choose another file' : 'Drop CSV or packet capture'}</strong>
              <span>or click to browse</span>
            </div>

            {file && (
              <div className="file-row">
                <div>
                  <span className="file-type"><Icon name="file" size={18} /></span>
                  <div><strong>{file.name}</strong><span>{formatBytes(file.size)} · ready</span></div>
                </div>
                <button type="button" className="text-button" onClick={() => { setFile(null); setError(''); }} disabled={busy}>Remove</button>
              </div>
            )}

            {error && (
              <div className="inline-alert" role="alert">
                <strong>Unable to analyse this file</strong>
                <span>{error}</span>
              </div>
            )}

            <div className="upload-actions">
              <button type="submit" className="button primary" disabled={!file || busy} aria-busy={busy}>
                {busy ? <><span className="busy-dot" />Analysing</> : <><Icon name="forecast" size={17} />Run forecast</>}
              </button>
              {busy
                ? <button type="button" className="button secondary" onClick={() => abortRef.current?.abort()}>Cancel</button>
                : <button type="button" className="button secondary" onClick={loadSample}>Use sample</button>}
            </div>

            <p className="privacy-note"><Icon name="shield" size={15} />Local processing only.</p>
          </form>

          <div className="forecast-output" id="forecast-results">
            {result ? (
              <div className="results-enter" ref={resultRef} tabIndex="-1">
                <div className={highRisk ? 'result-overview high-risk' : 'result-overview'}>
                  <div>
                    <span className="result-state"><Icon name={highRisk ? 'pulse' : 'shield'} size={18} />{forecastAvailable ? (highRisk ? 'Threshold crossed' : 'Below threshold') : 'Forecast unavailable'}</span>
                    <h2>{forecastAvailable ? 'Validated threat forecast' : 'More history required'}</h2>
                  </div>
                  <dl className="key-readings">
                    <div><dt>60-second risk</dt><dd>{riskValue}</dd></div>
                    <div><dt>Threshold</dt><dd>{thresholdValue}</dd></div>
                    <div><dt>Likely stage</dt><dd>{stageValue}</dd></div>
                    <div><dt>Latency</dt><dd>{Math.round(prediction?.latencyMs || 0)} ms</dd></div>
                  </dl>
                </div>

                <div className={`quality-callout quality-${prediction?.quality || 'ok'}`} role="status">
                  <QualityBadge quality={prediction?.quality} detail={prediction?.qualityDetail} />
                  <p>{prediction?.quality === 'ok'
                    ? 'Input quality is within the trusted range.'
                    : 'Input is outside the trusted training range. Verify against packet evidence.'}</p>
                </div>

                <ProbabilityTimeline prediction={prediction} />
              </div>
            ) : (
              <section className="panel forecast-empty" aria-labelledby="empty-title">
                <span className="empty-icon"><Icon name="forecast" size={28} /></span>
                <div>
                  <h2 id="empty-title">Forecast output</h2>
                  <p>Upload traffic or use the sample to generate the 10, 30, and 60-second forecast.</p>
                </div>
              </section>
            )}
          </div>
        </section>

        {result && (
          <section className="evidence-layout" aria-label="Forecast evidence">
            <StageAnnotations prediction={prediction} />
            <NarrativePanel narrative={result.narrative} />
            <FlaggedFlowsTable features={prediction?.topFeatures || []} />
          </section>
        )}

        <LiveDashboard />
      </main>
    </div>
  );
}

function getInitialRoute() {
  const dashboardHashes = ['#dashboard', '#forecast-workspace', '#forecast-results', '#live-capture'];
  return dashboardHashes.includes(window.location.hash) ? 'dashboard' : 'landing';
}

function App() {
  const [route, setRoute] = useState(getInitialRoute);

  useEffect(() => {
    const handleHashChange = () => {
      if (window.location.hash === '#dashboard') setRoute('dashboard');
      if (window.location.hash === '#home' || window.location.hash === '') setRoute('landing');
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const enterDashboard = () => {
    const navigate = () => {
      window.history.pushState(null, '', '#dashboard');
      setRoute('dashboard');
      window.scrollTo({ top: 0, behavior: 'instant' });
    };

    if (document.startViewTransition) {
      document.startViewTransition(navigate);
    } else {
      navigate();
    }
  };

  return route === 'dashboard' ? <Dashboard /> : <LandingPage onEnter={enterDashboard} />;
}

export default App;
