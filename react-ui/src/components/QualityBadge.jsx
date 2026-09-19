import React from 'react';

const QUALITY_COPY = {
  ok: 'Live quality · ok — window matches training distribution.',
  degraded: 'Live quality · degraded — treat this prediction with caution.',
  unreliable: 'Live quality · unreliable — do not act on this prediction alone.',
};

function QualityBadge({ quality = 'ok', detail }) {
  const tone = quality === 'ok' ? 'quality-ok' : quality === 'degraded' ? 'quality-degraded' : 'quality-unreliable';
  const title = detail
    ? `max|z| ${Number(detail.max_abs_z).toFixed(2)}, frac|z|>5 ${(Number(detail.frac_z_gt_5) * 100).toFixed(2)}% over ${detail.checked_features} features`
    : QUALITY_COPY[quality] || quality;
  return (
    <span className={`quality-badge ${tone}`} role="status" title={title}>
      <span aria-hidden="true">{quality === 'ok' ? '●' : quality === 'degraded' ? '▲' : '■'}</span>
      {`Live quality · ${quality}`}
    </span>
  );
}

export default QualityBadge;
