import React, { useEffect, useState } from 'react';

const THEME_KEY = 'kairos-theme';

function getLandingTheme() {
  try {
    const stored = window.localStorage.getItem(THEME_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch {
    // Storage can be unavailable in privacy-restricted browser sessions.
  }
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function ThemeIcon({ theme }) {
  return theme === 'dark' ? (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4" />
      <circle cx="12" cy="12" r="4" />
    </svg>
  ) : (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M20.4 15.2A8.5 8.5 0 0 1 8.8 3.6 8.5 8.5 0 1 0 20.4 15.2Z" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 12h14M14 7l5 5-5 5" />
    </svg>
  );
}

function KairosMark() {
  return (
    <span className="landing-mark" aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  );
}

function ThreatField() {
  const handlePointerMove = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width - 0.5) * 2;
    const y = ((event.clientY - bounds.top) / bounds.height - 0.5) * 2;
    event.currentTarget.style.setProperty('--pointer-x', x.toFixed(3));
    event.currentTarget.style.setProperty('--pointer-y', y.toFixed(3));
  };

  const resetPointer = (event) => {
    event.currentTarget.style.setProperty('--pointer-x', 0);
    event.currentTarget.style.setProperty('--pointer-y', 0);
  };

  return (
    <div
      className="threat-field"
      onPointerMove={handlePointerMove}
      onPointerLeave={resetPointer}
      role="img"
      aria-label="Illustration of network traffic becoming a rising 10, 30, and 60-second threat forecast"
    >
      <div className="threat-field__frame">
        <div className="threat-field__header">
          <span>Illustrative forecast</span>
          <strong>60s horizon</strong>
        </div>

        <div className="threat-field__plane">
          <svg className="threat-field__svg" viewBox="0 0 800 560" aria-hidden="true">
            <g className="threat-field__grid">
              <path d="M40 88H760M40 184H760M40 280H760M40 376H760M40 472H760" />
              <path d="M140 40V510M280 40V510M420 40V510M560 40V510M700 40V510" />
            </g>

            <g className="threat-field__network">
              <path d="M80 346 170 242 258 304 350 178" />
              <path d="M80 346 184 420 276 368 350 178" />
              <path d="M170 242 184 420M258 304 276 368" />
              <circle cx="80" cy="346" r="11" />
              <circle cx="170" cy="242" r="9" />
              <circle cx="184" cy="420" r="8" />
              <circle cx="258" cy="304" r="8" />
              <circle cx="276" cy="368" r="7" />
              <circle className="threat-field__focus-node" cx="350" cy="178" r="14" />
              <circle className="threat-field__pulse" cx="350" cy="178" r="30" />
            </g>

            <g className="threat-field__packets">
              <circle r="5">
                <animateMotion dur="3.8s" repeatCount="indefinite" path="M80 346 170 242 258 304 350 178" />
              </circle>
              <circle r="4">
                <animateMotion begin="-1.9s" dur="4.8s" repeatCount="indefinite" path="M80 346 184 420 276 368 350 178" />
              </circle>
            </g>

            <line className="threat-field__threshold" x1="350" y1="254" x2="746" y2="254" />
            <text className="threat-field__threshold-label" x="735" y="240" textAnchor="end">calibrated threshold</text>

            <path className="threat-field__forecast-area" d="M350 420 C404 412 418 374 460 364 S520 330 548 300 S610 206 650 222 S704 132 746 104 L746 472 L350 472Z" />
            <path className="threat-field__forecast-line" d="M350 420 C404 412 418 374 460 364 S520 330 548 300 S610 206 650 222 S704 132 746 104" />
            <g className="threat-field__horizons">
              <line x1="460" y1="364" x2="460" y2="472" />
              <line x1="548" y1="300" x2="548" y2="472" />
              <line x1="746" y1="104" x2="746" y2="472" />
              <circle cx="460" cy="364" r="6" />
              <circle cx="548" cy="300" r="6" />
              <circle cx="746" cy="104" r="7" />
              <text x="460" y="500" textAnchor="middle">10s</text>
              <text x="548" y="500" textAnchor="middle">30s</text>
              <text x="746" y="500" textAnchor="middle">60s</text>
            </g>
          </svg>
          <span className="threat-field__scan" aria-hidden="true" />
        </div>

        <div className="threat-field__footer">
          <span>Observed traffic</span>
          <span>Predicted future</span>
        </div>
      </div>
    </div>
  );
}

function LandingPage({ onEnter }) {
  const [theme, setTheme] = useState(getLandingTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    try {
      window.localStorage.setItem(THEME_KEY, theme);
    } catch {
      // The selected theme still applies for this session.
    }
    document.title = 'KAIROS — Predictive network defence';
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#090a0c' : '#eef0f2');
  }, [theme]);

  return (
    <main className="landing-page" id="home">
      <nav className="landing-nav" aria-label="Primary navigation">
        <a className="landing-brand" href="#home" aria-label="KAIROS home">
          <KairosMark />
          <span>KAIROS</span>
        </a>
        <div className="landing-nav__links">
          <a href="#capabilities">Capabilities</a>
          <a href="#method">Method</a>
        </div>
        <div className="landing-nav__actions">
          <button className="landing-theme-toggle" type="button" onClick={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}>
            <ThemeIcon theme={theme} />
          </button>
          <button className="landing-nav__cta" type="button" onClick={onEnter}>
            Open dashboard <ArrowIcon />
          </button>
        </div>
      </nav>

      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-hero__copy">
          <div className="landing-hero__signal" aria-hidden="true"><span /> Predictive network defence</div>
          <h1 id="landing-title">See the attack<span>before it arrives.</span></h1>
          <p>KAIROS transforms ordered network traffic into calibrated 10, 30, and 60-second threat forecasts—locally, with evidence an analyst can verify.</p>
          <div className="landing-hero__actions">
            <button className="landing-primary-action" type="button" onClick={onEnter}>Open threat console <ArrowIcon /></button>
            <a className="landing-text-link" href="#capabilities">Explore the system</a>
          </div>
          <p className="landing-hero__proof">Built for SIH 26153 · Offline-first · Analyst-in-the-loop</p>
        </div>
        <ThreatField />
      </section>

      <section className="landing-capabilities" id="capabilities" aria-labelledby="capability-title">
        <header className="landing-section-heading">
          <h2 id="capability-title">Built for the decision before the incident.</h2>
          <p>One focused workflow—from captured traffic to an explainable warning.</p>
        </header>
        <div className="landing-capability-list">
          <article><span>01</span><div><h3>Forecast future risk</h3><p>Compare validated 10, 30, and 60-second horizons against a calibrated decision threshold.</p></div></article>
          <article><span>02</span><div><h3>Explain the evidence</h3><p>Expose stage coverage, input quality, and the traffic features driving each prediction.</p></div></article>
          <article><span>03</span><div><h3>Operate locally</h3><p>Inspect CSV, PCAP, and PCAPNG evidence without sending sensitive network data away.</p></div></article>
        </div>
      </section>

      <section className="landing-method" id="method" aria-labelledby="method-title">
        <div className="landing-method__copy"><h2 id="method-title">From packet evidence to a calibrated warning.</h2><p>KAIROS preserves temporal order so the forecast describes what may happen next—not only what is happening now.</p></div>
        <ol className="landing-method__track">
          <li><span>01</span><strong>Traffic</strong></li>
          <li><span>02</span><strong>Ordered 10s windows</strong></li>
          <li><span>03</span><strong>Graph context</strong></li>
          <li><span>04</span><strong>10 / 30 / 60s forecast</strong></li>
        </ol>
      </section>

      <section className="landing-final-cta" aria-labelledby="final-cta-title">
        <div><h2 id="final-cta-title">Move from reaction to anticipation.</h2><p>Bring network evidence into a focused, explainable forecasting workspace.</p></div>
        <button className="landing-primary-action" type="button" onClick={onEnter}>Enter KAIROS <ArrowIcon /></button>
      </section>

      <footer className="landing-footer"><span>KAIROS · AI-based network attack forecasting</span><span>SIH Problem Statement 26153</span></footer>
    </main>
  );
}

export default LandingPage;
