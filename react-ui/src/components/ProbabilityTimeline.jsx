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

const ALERT_THRESHOLD = 0.6;

function ProbabilityTimeline({ prediction }) {
  const future = prediction?.rollout?.probabilities || [];
  const data = [
    { horizon: 'Now', probability: prediction?.probability ?? 0, kind: 'Observed state' },
    ...future.map((probability, index) => ({
      horizon: `T+${index + 1}`,
      probability,
      kind: 'Simulated future',
    })),
  ];

  return (
    <section className="panel timeline-panel" aria-labelledby="timeline-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Forecast tape / probability</p>
          <h2 id="timeline-title">Risk trajectory</h2>
        </div>
        <div className="chart-legend" aria-label="Chart legend">
          <span><i className="legend-current" /> current</span>
          <span><i className="legend-future" /> simulated</span>
        </div>
      </div>
      <div className="chart-frame" role="img" aria-label="Current and projected malicious activity probability">
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
            <YAxis
              domain={[0, 1]}
              tickFormatter={(value) => `${Math.round(value * 100)}%`}
              ticks={[0, 0.25, 0.5, 0.75, 1]}
              tickLine={false}
              axisLine={false}
              width={44}
            />
            <Tooltip
              formatter={(value) => [`${(value * 100).toFixed(1)}%`, 'Risk']}
              labelFormatter={(label, payload) =>
                `${label} · ${payload?.[0]?.payload?.kind || 'Forecast'}`
              }
              contentStyle={{ background: '#FFFEF8', border: '1px solid #10243E', borderRadius: 4 }}
            />
            <ReferenceLine
              y={ALERT_THRESHOLD}
              stroke="#C43D2B"
              strokeDasharray="7 5"
              label={{ value: '60% ALERT', position: 'insideTopRight', fill: '#8E2E22', fontSize: 11 }}
            />
            <Area type="monotone" dataKey="probability" fill="url(#riskWash)" stroke="none" />
            <Line
              type="monotone"
              dataKey="probability"
              stroke="#2459D3"
              strokeWidth={3}
              dot={{ r: 4, fill: '#FFFEF8', stroke: '#2459D3', strokeWidth: 2 }}
              activeDot={{ r: 6, fill: '#2459D3' }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="chart-note">T+ windows are autoregressive simulations, not observed traffic.</p>
    </section>
  );
}

export default ProbabilityTimeline;
