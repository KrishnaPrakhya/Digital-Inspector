import Link from "next/link";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="shell footer-grid">
        <div>
          <div className="brand">
            <span className="brand-mark">DI</span>
            <span>Digital Inspector</span>
          </div>
          <p>
            AI-assisted scam evidence analysis for public safety. Not a
            substitute for police, bank, or legal advice.
          </p>
        </div>
        <div>
          <b>Product</b>
          <Link href="/analyze">Analyze evidence</Link>
          <Link href="/pulse">Scam pulse</Link>
          <Link href="/library">Scam library</Link>
          <Link href="/landscape">Threat map</Link>
          <Link href="/dashboard">Local reports</Link>
        </div>
        <div>
          <b>Immediate help</b>
          <a href="tel:1930">Call 1930</a>
          <a href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">
            cybercrime.gov.in ↗
          </a>
          <span>Never share an OTP</span>
        </div>
      </div>
      <div className="shell footer-bottom">
        <span>Built for the NxtWave Idea2Impact hackathon.</span>
        <span>
          Evidence stays on this device unless you submit it for analysis.
        </span>
      </div>
    </footer>
  );
}
