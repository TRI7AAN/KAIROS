import React, { useEffect, useRef, useState } from 'react';
import FlaggedFlowsTable from './components/FlaggedFlowsTable';
import NarrativePanel from './components/NarrativePanel';
import ProbabilityTimeline from './components/ProbabilityTimeline';
import StageAnnotations from './components/StageAnnotations';
import { explainApiError, forecastTraffic } from './api/client';
import './styles.css';

const MAX_FILE_BYTES = 750 * 1024 * 1024;

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
}

function validateFile(file) {
  if (!file) return 'Choose a CICFlowMeter CSV to continue.';
  if (!file.name.toLowerCase().endsWith('.csv')) {
    return 'Use a .csv export from CICFlowMeter. Raw PCAP upload is not enabled yet.';
  }
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

  useEffect(() => {
    document.title = 'Forecast console — KAIROS';
    return () => abortRef.current?.abort();
  }, []);

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
    } catch (sampleError) {
      setError('The bundled sample could not be loaded. Refresh the dashboard and try again.');
      setBusy(false);
    }
  };

  const prediction = result?.prediction;
  const highRisk = (prediction?.probability || 0) >= 0.6;

  return (
    <div className="app-shell">
      <header className="masthead">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true"><span /><span /><span /></div>
          <div>
            <p className="eyebrow">Predictive network defence / SIH</p>
            <h1>KAIROS</h1>
          </div>
        </div>
        <div className="system-state">
          <span className="system-dot" aria-hidden="true" />
          <div>
            <strong>Offline core</strong>
            <span>Cloud independent by default</span>
          </div>
        </div>
      </header>

      <main>
        <section className="hero" aria-labelledby="hero-title">
          <div>
            <p className="hero-index">FORECAST CONSOLE · 01</p>
            <h2 id="hero-title">See the attack path<br /><em>before impact.</em></h2>
          </div>
          <p className="hero-copy">
            Upload CICFlowMeter traffic. KAIROS models how the network state may evolve,
            rolls it forward five windows, and returns an explainable analyst briefing.
          </p>
        </section>

        <section className="intake-grid" aria-label="Traffic analysis input">
          <form
            className="upload-panel"
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              runForecast();
            }}
          >
            <div className="section-number">01 / INGEST</div>
            <h2>Traffic evidence</h2>
            <p className="section-intro">One CICFlowMeter CSV, processed locally through the Java and Python services.</p>

            <label
              className={dragOver ? 'drop-zone drag-over' : 'drop-zone'}
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
                type="file"
                accept=".csv,text/csv"
                onChange={(event) => chooseFile(event.target.files?.[0])}
                disabled={busy}
              />
              <span className="upload-glyph" aria-hidden="true">↥</span>
              <strong>{file ? 'Replace traffic file' : 'Choose traffic file'}</strong>
              <span>or drag a CSV here · maximum 750 MiB</span>
            </label>

            {file && (
              <div className="file-row">
                <div>
                  <span className="file-type">CSV</span>
                  <div>
                    <strong>{file.name}</strong>
                    <span>{formatBytes(file.size)} · ready for local analysis</span>
                  </div>
                </div>
                <button
                  type="button"
                  className="text-button"
                  onClick={() => {
                    setFile(null);
                    setError('');
                  }}
                  disabled={busy}
                >
                  Remove
                </button>
              </div>
            )}

            {error && (
              <div className="inline-alert" role="alert">
                <strong>Analysis needs attention</strong>
                <span>{error}</span>
              </div>
            )}

            <div className="upload-actions">
              <button
                type="submit"
                className="button primary"
                disabled={!file || busy}
                aria-busy={busy}
              >
                {busy ? <><span className="busy-dot" /> Analysing traffic</> : 'Run 5-window forecast'}
              </button>
              {busy ? (
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => abortRef.current?.abort()}
                >
                  Cancel
                </button>
              ) : (
                <button type="button" className="button secondary" onClick={loadSample}>
                  Load sample attack
                </button>
              )}
            </div>
            <p className="privacy-note"><span aria-hidden="true">⌁</span> Your file is sent only to the local KAIROS engine.</p>
          </form>

          <aside className="method-panel" aria-labelledby="method-title">
            <div className="section-number">MODEL ROUTE / VERIFIED</div>
            <h2 id="method-title">From flow to foresight</h2>
            <ol className="route-list">
              <li><span>01</span><div><strong>Window the traffic</strong><p>Aggregate flows into ordered 10-second network states.</p></div></li>
              <li><span>02</span><div><strong>Encode the graph</strong><p>Capture host-flow structure and temporal context.</p></div></li>
              <li><span>03</span><div><strong>Roll the world forward</strong><p>Simulate T+1 through T+5 without retraining.</p></div></li>
              <li><span>04</span><div><strong>Explain the warning</strong><p>Rank SHAP evidence and generate a local briefing.</p></div></li>
            </ol>
            <div className="method-proof">
              <span>CORE PROMISE</span>
              <strong>Forecast, not present-state classification.</strong>
            </div>
          </aside>
        </section>

        {result ? (
          <section className="results" aria-labelledby="result-title">
            <div className="result-ribbon" ref={resultRef} tabIndex="-1">
              <div>
                <p className="eyebrow">Latest inference / {result.artifactVersion}</p>
                <h2 id="result-title">{highRisk ? 'Escalation threshold crossed' : 'Below escalation threshold'}</h2>
              </div>
              <div className={highRisk ? 'risk-stamp high' : 'risk-stamp low'}>
                <span>Forecast risk</span>
                <strong>{((prediction?.probability || 0) * 100).toFixed(1)}%</strong>
              </div>
              <dl className="result-facts">
                <div><dt>Next stage</dt><dd>{(prediction?.predictedStage || 'unknown').replaceAll('_', ' ')}</dd></div>
                <div><dt>Peak rollout</dt><dd>{((prediction?.rollout?.maxProbability || 0) * 100).toFixed(1)}%</dd></div>
                <div><dt>Inference</dt><dd>{Math.round(prediction?.latencyMs || 0)} ms</dd></div>
              </dl>
            </div>
            <div className="result-grid">
              <ProbabilityTimeline prediction={prediction} />
              <StageAnnotations prediction={prediction} />
              <NarrativePanel narrative={result.narrative} />
              <FlaggedFlowsTable features={prediction?.topFeatures || []} />
            </div>
          </section>
        ) : (
          <section className="empty-workbench" aria-label="No forecast yet">
            <span>02 / FORECAST</span>
            <div>
              <strong>The analysis workbench is ready.</strong>
              <p>Run a traffic file or the bundled sample to reveal the trajectory, stage outlook, and evidence.</p>
            </div>
          </section>
        )}
      </main>

      <footer>
        <span>KAIROS · Network Attack World Model</span>
        <span>Explainable · offline-first · analyst verified</span>
      </footer>
    </div>
  );
}

export default App;
