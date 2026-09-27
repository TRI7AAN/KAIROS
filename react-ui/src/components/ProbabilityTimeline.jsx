import React from 'react';
import {
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
  const shouldAnimate = typeof window !== 'undefined'
    && !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const data = horizons.map((item) => ({
    horizon: `${Math.round(item.horizonSeconds)}s`,
    probability: item.probability,
    threshold: item.threshold,
    stage: item.predictedStageIfAttack,
  }));

  return (
    <section className="panel timeline-panel" aria-labelledby="timeline-title">
      <div className="panel-heading timeline-heading">
        <div>
          <h2 id="timeline-title">Future attack probability</h2>
          <p>Validated 10, 30, and 60-second horizons</p>
        </div>
        {forecast?.available && (
          <div className="chart-legend" aria-label="Chart legend">
            <span><i className="legend-future" />Forecast</span>
            <span><i className="legend-threshold" />Threshold</span>
          </div>
        )}
      </div>

      {forecast?.available ? (
        <>
          <div className="chart-frame" role="img" aria-label="Validated future attack probabilities at 10, 30, and 60 seconds">
            <ResponsiveContainer width="100%" height={430}>
              <ComposedChart data={data} margin={{ top: 28, right: 24, bottom: 10, left: 4 }}>
                <CartesianGrid stroke="#292A2E" strokeDasharray="2 7" vertical={false} />
                <XAxis
                  dataKey="horizon"
                  tick={{ fill: '#8B8E95', fontSize: 12 }}
                  tickLine={false}
                  axisLine={{ stroke: '#3A3C42' }}
                  padding={{ left: 28, right: 28 }}
                />
                <YAxis
                  domain={[0, 1]}
                  tick={{ fill: '#8B8E95', fontSize: 12 }}
                  tickFormatter={(value) => `${Math.round(value * 100)}%`}
                  ticks={[0, 0.25, 0.5, 0.75, 1]}
                  tickLine={false}
                  axisLine={false}
                  width={48}
                />
                <Tooltip
                  formatter={(value) => [`${(value * 100).toFixed(1)}%`, 'Future risk']}
                  labelFormatter={(label, payload) => `${label} · ${payload?.[0]?.payload?.stage?.replaceAll('_', ' ') || 'forecast'}`}
                  contentStyle={{ background: '#17181A', border: '1px solid #3A3C42', borderRadius: 8, color: '#F0F0F1' }}
                  cursor={{ stroke: '#505259', strokeDasharray: '3 5' }}
                />
                <ReferenceLine
                  y={threshold}
                  stroke="#B67C80"
                  strokeWidth={1.5}
                  strokeDasharray="7 6"
                  label={{ value: `${(threshold * 100).toFixed(1)}% threshold`, position: 'insideTopRight', fill: '#B67C80', fontSize: 12 }}
                />
                <Line
                  type="monotone"
                  dataKey="probability"
                  stroke="#D6D7DA"
                  strokeWidth={3}
                  dot={{ r: 6, fill: '#111214', stroke: '#D6D7DA', strokeWidth: 3 }}
                  activeDot={{ r: 8, fill: '#D6D7DA', stroke: '#111214', strokeWidth: 3 }}
                  isAnimationActive={shouldAnimate}
                  animationDuration={520}
                  animationEasing="ease-out"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <div className="horizon-readout" aria-label="Exact forecast values">
            {horizons.map((item) => (
              <div key={item.horizonSeconds} className={item.alert ? 'alert' : ''}>
                <span>{Math.round(item.horizonSeconds)} seconds</span>
                <strong>{(item.probability * 100).toFixed(1)}%</strong>
                <small>{item.alert ? 'Above threshold' : 'Below threshold'} · {(item.threshold * 100).toFixed(1)}%</small>
              </div>
            ))}
          </div>

          <p className="chart-note">Calibrated ExtraTrees temporal forecast. Values support investigation; they do not confirm an attack.</p>
        </>
      ) : (
        <div className="forecast-unavailable" role="status">
          <strong>Validated forecast unavailable</strong>
          <span>{forecast?.detail || `Reason: ${forecast?.reason || 'unknown'}.`}</span>
          <span>{forecast?.receivedHistoryWindows || 0} of {forecast?.requiredHistoryWindows || 0} history windows received.</span>
        </div>
      )}

      <details className="diagnostic-disclosure">
        <summary>World-model diagnostic</summary>
        <p>
          Immediate GNN-Transformer score: {((prediction?.probability || 0) * 100).toFixed(1)}%.
          Autoregressive rollout peak: {((prediction?.rollout?.maxProbability || 0) * 100).toFixed(1)}%.
          These are transition diagnostics, not the primary forecast.
        </p>
      </details>
    </section>
  );
}

export default ProbabilityTimeline;
