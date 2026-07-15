import Link from "next/link";

import { LandingHero } from "@/components/LandingHero";
import { FAMILY_META, PLAYBOOKS } from "@/lib/scam-content";

const steps = [
  ["01", "Share the evidence", "Record or upload a call, paste a message, or scan a chat screenshot on-device."],
  ["02", "Trace the playbook", "Separate AI models identify the scam family and the pressure stage of every utterance."],
  ["03", "Preserve what matters", "UPI IDs, phone numbers, amounts, agencies, apps, and links are extracted without an LLM."],
  ["04", "Act inside the hour", "Call 1930 and carry a deterministic, pre-filled complaint to the national portal."],
];

export default function Home() {
  return <main>
    <LandingHero />
    <section className="impact-band"><div><strong>7</strong><span>call categories</span></div><div><strong>6</strong><span>playbook stages</span></div><div><strong>3 AI</strong><span>ONNX models</span></div><div><strong>1930</strong><span>national helpline</span></div></section>
    <section className="shell section">
      <div className="section-heading split-heading"><div><span>Designed for the crisis moment</span><h2>One flow, from doubt to action.</h2></div><p>Scammers win by compressing time and attention. The interface slows the situation down, shows exactly what is happening, and keeps the next action unmistakable.</p></div>
      <div className="step-grid four">{steps.map(([number, title, copy]) => <article className="step-card" key={number}><b>{number}</b><h3>{title}</h3><p>{copy}</p></article>)}</div>
    </section>
    <section className="section surface-section"><div className="shell"><div className="section-heading split-heading"><div><span>Indian scam playbooks</span><h2>Recognize the script before it reaches payment.</h2></div><Link className="text-link" href="/library">Explore the full library →</Link></div><div className="family-grid">{PLAYBOOKS.map((playbook) => { const meta = FAMILY_META[playbook.family]; return <Link href={`/library#${playbook.family}`} className="family-card" key={playbook.family} style={{ "--accent": meta.color } as React.CSSProperties}><div className="family-icon">{meta.name.slice(0, 2).toUpperCase()}</div><div><h3>{meta.name}</h3><p>{meta.short}</p></div><span>→</span></Link>; })}</div></div></section>
    <section className="shell section emergency-card"><div><span className="eyebrow plain">Money already sent?</span><h2>Do not wait for another call.</h2><p>Contact the national cyber-fraud helpline immediately and notify your bank through an official channel. Preserve transaction IDs, numbers, screenshots, and recordings.</p></div><div className="emergency-actions"><a className="button primary" href="tel:1930">Call 1930 now</a><a className="button secondary" href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">Open reporting portal ↗</a></div></section>
  </main>;
}
