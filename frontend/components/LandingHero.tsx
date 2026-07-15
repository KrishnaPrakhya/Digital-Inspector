"use client";

import { motion } from "framer-motion";
import Link from "next/link";

const stages = ["Authority", "Threat", "Isolation", "Information", "Payment"];

export function LandingHero() {
  return <section className="hero shell hero-grid">
    <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .55 }}>
      <div className="eyebrow"><span /> India-focused scam intelligence</div>
      <h1>Hear the pressure.<br /><em>See the playbook.</em><br />Stop the transfer.</h1>
      <p className="hero-copy">Turn a suspicious call, message, or screenshot into a clear scam verdict, escalation timeline, extracted evidence, and an action-ready complaint.</p>
      <div className="hero-actions"><Link className="button primary" href="/analyze">Analyze evidence <span>→</span></Link><Link className="button secondary" href="/library">Learn the red flags</Link></div>
      <div className="hero-trust"><span>✓ Family + stage AI</span><span>✓ Hinglish-aware</span><span>✓ Deterministic complaint</span></div>
    </motion.div>
    <motion.div className="hero-console" initial={{ opacity: 0, scale: .96 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: .15, duration: .6 }}>
      <div className="console-head"><span><i /> Analysis in progress</span><small>REQUEST 7F2A</small></div>
      <div className="console-wave">{Array.from({ length: 48 }, (_, i) => <motion.i key={i} initial={{ height: 3 }} animate={{ height: 8 + ((i * 17) % 38) }} transition={{ delay: i * .018, duration: .25 }} />)}</div>
      <div className="console-verdict"><div><small>DETECTED PATTERN</small><strong>Digital arrest</strong></div><span>94%</span></div>
      <div className="console-risk"><span>Risk level</span><div><i /></div><b>92 / 100</b></div>
      <div className="console-stages">{stages.map((stage, index) => <div className={index < 4 ? "lit" : ""} key={stage}><i>{index + 1}</i><span>{stage}</span></div>)}</div>
      <div className="console-action"><b>Golden-hour action ready</b><span>Complaint evidence assembled · Call 1930</span></div>
    </motion.div>
  </section>;
}
