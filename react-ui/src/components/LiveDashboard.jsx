import React, { useEffect, useRef, useState } from 'react';
import ProbabilityTimeline from './ProbabilityTimeline';
import QualityBadge from './QualityBadge';
import StageAnnotations from './StageAnnotations';
import {
  explainApiError,
  listLiveInterfaces,
  liveSessionStatus,
  openLiveEvents,
  startLiveSession,
  stopLiveSession,
} from '../api/client';

function LiveDashboard() {
  const [interfaces, setInterfaces] = useState([]);
  const [interfaceName, setInterfaceName] = useState('lo');
  const [durationSeconds, setDurationSeconds] = useState(60);
  const [packetLimit, setPacketLimit] = useState('');
  const [bpfFilter, setBpfFilter] = useState('');
  const [session, setSession] = useState(null);
  const [counters, setCounters] = useState(null);
  const [predictions, setPredictions] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(false);
  const closeRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    listLiveInterfaces()
      .then((found) => {
        if (cancelled) return;
        setInterfaces(found);
        if (found.some((info) => info.name === 'lo')) setInterfaceName('lo');
        else if (found.length > 0) setInterfaceName(found[0].name);
      })
      .catch((requestError) => {
        if (!cancelled) setError(explainApiError(requestError));
      });

    return () => {
      cancelled = true;
      closeRef.current?.();
    };
  }, []);

  const disconnect = () => {
    closeRef.current?.();
    closeRef.current = null;
    setConnected(false);
  };

  const start = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');

    try {
      const created = await startLiveSession({
        interfaceName,
        durationSeconds: Number(durationSeconds) || undefined,
        packetLimit: packetLimit === '' ? undefined : Number(packetLimit),
        bpfFilter: bpfFilter || undefined,
      });
      setSession(created);
      setPredictions([]);
      setCounters({
        packetCount: created.packetCount || 0,
        dropCount: created.dropCount || 0,
        windowCount: 0,
        state: created.state,
      });
      disconnect();
      closeRef.current = openLiveEvents(created.sessionId, {
        onState: (view) => {
          setSession(view);
          setCounters((prior) => ({ ...(prior || {}), ...view }));
        },
        onCounter: (counts) => setCounters((prior) => ({ ...(prior || {}), ...counts })),
        onPrediction: (item) => setPredictions((prior) => [...prior.slice(-11), item]),
        onError: () => setConnected(false),
      });
      setConnected(true);
    } catch (requestError) {
      setError(explainApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    if (!session) return;
    setBusy(true);
    try {
      const stopped = await stopLiveSession(session.sessionId);
      setSession(stopped);
      disconnect();
      const refreshed = await liveSessionStatus(session.sessionId).catch(() => stopped);
      setSession(refreshed);
    } catch (requestError) {
      setError(explainApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  const latest = predictions[predictions.length - 1]?.prediction;
  const quality = predictions[predictions.length - 1]?.quality || latest?.quality || 'ok';

  return (
    <details className="panel live-panel" id="live-capture">
      <summary>
        <div>
          <h2>Live capture</h2>
          <p>Optional passive monitoring</p>
        </div>
        <span className="live-summary-state">{session?.state || 'Configure session'}</span>
      </summary>

      <div className="live-content">
        <div className="live-heading">
          <p>Capture traffic from a local interface and stream forecast windows over SSE.</p>
          {latest && <QualityBadge quality={quality} detail={latest?.qualityDetail} />}
        </div>

        <form className="live-controls" onSubmit={start} noValidate>
          <label htmlFor="live-interface">
            Interface
            <select id="live-interface" value={interfaceName} onChange={(event) => setInterfaceName(event.target.value)} disabled={busy || !!session?.state?.match(/CAPTURING|STARTING/)}>
              {interfaces.map((info) => (
                <option key={info.name} value={info.name}>
                  {info.name}{info.loopback ? ' (loopback)' : ''}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor="live-duration">
            Duration (s)
            <input id="live-duration" type="number" min="1" max="3600" value={durationSeconds} onChange={(event) => setDurationSeconds(event.target.value)} disabled={busy} />
          </label>
          <label htmlFor="live-packet-limit">
            Packet limit
            <input id="live-packet-limit" type="number" min="1" max="1000000" placeholder="Optional" value={packetLimit} onChange={(event) => setPacketLimit(event.target.value)} disabled={busy} />
          </label>
          <label className="live-filter" htmlFor="live-bpf-filter">
            BPF filter
            <input id="live-bpf-filter" type="text" placeholder="e.g. udp port 9999" value={bpfFilter} onChange={(event) => setBpfFilter(event.target.value)} disabled={busy} />
          </label>
          <div className="upload-actions">
            <button type="submit" className="button primary" disabled={busy || session?.state === 'CAPTURING'}>
              {busy ? 'Starting…' : 'Start capture'}
            </button>
            <button type="button" className="button secondary" onClick={stop} disabled={busy || !session || session.state === 'STOPPED'}>
              Stop
            </button>
          </div>
        </form>

        {error && (
          <div className="inline-alert" role="alert">
            <strong>Live capture unavailable</strong>
            <span>{error}</span>
          </div>
        )}

        <dl className="live-counters">
          <div><dt>State</dt><dd>{session?.state || 'idle'}</dd></div>
          <div><dt>Stream</dt><dd>{connected ? 'connected' : 'disconnected'}</dd></div>
          <div><dt>Packets</dt><dd>{counters?.packetCount ?? 0}</dd></div>
          <div><dt>Drops</dt><dd>{counters?.dropCount ?? 0}</dd></div>
          <div><dt>Windows</dt><dd>{predictions.length}</dd></div>
        </dl>

        {latest && (
          <div className="live-results">
            <ProbabilityTimeline prediction={latest} />
            <StageAnnotations prediction={latest} />
          </div>
        )}
      </div>
    </details>
  );
}

export default LiveDashboard;
