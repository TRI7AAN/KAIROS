import React from 'react';

function humanize(value = '') {
  return value.replaceAll('_', ' ').replaceAll('.', ' · ');
}

function FlaggedFlowsTable({ features = [] }) {
  return (
    <section className="panel evidence-panel" aria-labelledby="evidence-title">
      <div className="panel-heading">
        <div>
          <h2 id="evidence-title">Forecast drivers</h2>
          <p className="panel-subtitle">SHAP / ranked evidence</p>
        </div>
        <span className="count-mark">{features.length} signals</span>
      </div>
      <div className="table-scroll">
        <table>
          <caption className="sr-only">Top model feature contributions for this forecast</caption>
          <thead>
            <tr>
              <th scope="col">Rank</th>
              <th scope="col">Feature</th>
              <th scope="col">Observed value</th>
              <th scope="col">SHAP contribution</th>
              <th scope="col">Direction</th>
            </tr>
          </thead>
          <tbody>
            {features.length === 0 ? (
              <tr><td colSpan="5" className="empty-cell">No feature contributions were returned.</td></tr>
            ) : features.map((item, index) => {
              const positive = item.shapValue >= 0;
              return (
                <tr key={`${item.feature}-${index}`}>
                  <td className="rank-cell">{String(index + 1).padStart(2, '0')}</td>
                  <td><strong>{humanize(item.feature)}</strong></td>
                  <td className="numeric">{Number(item.value).toFixed(3)}</td>
                  <td className="numeric">{Number(item.shapValue).toFixed(4)}</td>
                  <td>
                    <span className={positive ? 'direction up' : 'direction down'}>
                      {positive ? '↑ raises risk' : '↓ lowers risk'}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="panel-note">Contributions explain this model output; they do not establish causality.</p>
    </section>
  );
}

export default FlaggedFlowsTable;
