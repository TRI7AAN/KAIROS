import React from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

function ProbabilityTimeline({ prediction }) {
  const forecast = prediction?.validatedForecast;
  const horizons = forecast?.horizons || [];
  const primary = forecast?.primary;
  const threshold = primary?.threshold ?? 0;
  const data = horizons.map((item) => ({
    horizon: `${Math.round(item.horizonSeconds)}s`,
    probability: item.probability,
    threshold: item.threshold,
    stage: item.predictedStageIfAttack,
  }));

  return (
    <section className="panel timeline-panel" aria-labelledby="timeline-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Validated temporal head / future probability</p>
          <h2 id="timeline-title">10 / 30 / 60-second forecast</h2>
        </div>
        {forecast?.available && (
          <div className="chart-legend" aria-label="Chart legend">
            <span><i className="legend-future" /> validated forecast</span>
            <span><i className="legend-threshold" /> calibrated threshold</span>
          </div>
        )}
      </div>

      {forecast?.available ? (
        <>
          <div className="forecast-cards" aria-label="Validated forecast horizons">
            {horizons.map((item) => (
              <article className={item.alert ? 'forecast-card alert' : 'forecast-card'} key={item.horizonSeconds}>
                <span>{Math.round(item.horizonSeconds)} seconds</span>
                <strong>{(item.probability * 100).toFixed(1)}%</strong>
                <small>
                  threshold {(item.threshold * 100).toFixed(1)}% · {item.alert ? 'alert' : 'below threshold'}
                </small>
              </article>
            ))}
          </div>
          <div className="chart-frame" role="img" aria-label="Validated future attack probabilities at 10, 30, and 60 seconds">
            <ResponsiveContainer width="100%" height={285}>
              <ComposedChart data={data} margin={{ top: 16, right: 16, bottom: 8, left: 0 }}>
                <defs>
                  <linearGradient id="riskWash" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#2459D3" stopOpacity={0.24} />
                    <stop offset="100%" stopColor="#2459D3" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#D8DCDB" strokeDasharray="2 5" vertical={false} />
                <XAxis dataKey="horizon" tickLine={false} axisLine={{ stroke: '#9BA7AE' }} />
                <YAxis domain={[0, 1]} tickFormatter={(value) => `${Math.round(value * 100)}%`} ticks={[0, 0.25, 0.5, 0.75, 1]} tickLine={false} axisLine={false} width={44} />
                <Tooltip
                  formatter={(value) => [`${(value * 100).toFixed(1)}%`, 'Future attack probability']}
                  labelFormatter={(label, payload) => `${label} · ${payload?.[0]?.payload?.stage?.replaceAll('_', ' ') || 'forecast'}`}
                  contentStyle={{ background: '#FFFEF8', border: '1px solid #10243E', borderRadius: 4 }}
                />
                <ReferenceLine y={threshold} stroke="#C43D2B" strokeDasharray="7 5" label={{ value: `${(threshold * 100).toFixed(1)}% THRESHOLD`, position: 'insideTopRight', fill: '#8E2E22', fontSize: 11 }} />
                <Area type="monotone" dataKey="probability" fill="url(#riskWash)" stroke="none" />
                <Line type="monotone" dataKey="probability" stroke="#2459D3" strokeWidth={3} dot={{ r: 4, fill: '#FFFEF8', stroke: '#2459D3', strokeWidth: 2 }} activeDot={{ r: 6, fill: '#2459D3' }} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="chart-note">Probabilities and alert thresholds come from the held-out, calibrated ExtraTrees temporal forecasting component.</p>
        </>
      ) : (
        <div className="forecast-unavailable" role="status">
          <strong>Validated forecast unavailable</strong>
          <span>{forecast?.detail || `Reason: ${forecast?.reason || 'unknown'}.`}</span>
          <span>{forecast?.receivedHistoryWindows || 0} of {forecast?.requiredHistoryWindows || 0} history windows received.</span>
        </div>
      )}

      <details className="diagnostic-disclosure">
        <summary>World-model rollout diagnostic</summary>
        <p>
          The GNN-Transformer immediate score is {((prediction?.probability || 0) * 100).toFixed(1)}%; its autoregressive rollout peaks at {((prediction?.rollout?.maxProbability || 0) * 100).toFixed(1)}%. These are transition diagnostics, not the primary calibrated forecast.
        </p>
      </details>
    </section>
  );
}

export default ProbabilityTimeline;
