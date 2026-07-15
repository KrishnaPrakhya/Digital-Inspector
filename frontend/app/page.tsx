import Link from "next/link";

const steps = [
  ["01", "Share the evidence", "Record or upload a call, paste a message, or scan a screenshot."],
  ["02", "AI traces the playbook", "Two classifiers identify the scam family and escalation stage."],
  ["03", "Act inside the golden hour", "Call 1930 and take a pre-filled complaint to the national portal."],
];

export default function Home() {
  return (
    <main>
      <section className="hero shell">
        <div className="eyebrow"><span /> Built for India&apos;s scam emergency</div>
        <h1>Stop the call.<br /><em>Trace the scam.</em><br />Act before the money moves.</h1>
        <p className="hero-copy">Digital Inspector analyzes suspicious calls and messages, exposes the scammer&apos;s playbook, and turns evidence into action.</p>
        <div className="hero-actions">
          <Link className="button primary" href="/analyze">Analyze evidence</Link>
          <a className="button secondary" href="tel:1930">Call 1930 now</a>
        </div>
        <div className="golden-note"><strong>The golden hour matters.</strong> Rapid reporting gives banks and authorities the best chance to interrupt the money trail.</div>
      </section>
      <section className="impact-band">
        <div><strong>7</strong><span>scam families</span></div>
        <div><strong>6</strong><span>playbook stages</span></div>
        <div><strong>3 min</strong><span>maximum evidence clip</span></div>
        <div><strong>1930</strong><span>national helpline</span></div>
      </section>
      <section className="shell section">
        <div className="section-heading"><span>How it works</span><h2>From uncertainty to a clear next move.</h2></div>
        <div className="step-grid">
          {steps.map(([number, title, copy]) => <article className="step-card" key={number}><b>{number}</b><h3>{title}</h3><p>{copy}</p></article>)}
        </div>
      </section>
    </main>
  );
}
