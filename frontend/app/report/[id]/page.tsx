"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";

import type { Entities, ScamFamily } from "@/lib/api";
import { FAMILY_META, STAGE_META } from "@/lib/scam-content";
import { generateComplaintPdf } from "@/lib/complaint-pdf";
import { getReport, type StoredReport } from "@/lib/storage";
import { useCountUp } from "@/lib/use-count-up";

const reveal = {
  hidden: { opacity: 0, y: 14 },
  show: (index: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: 0.06 * index, duration: 0.42, ease: [0.22, 1, 0.36, 1] as const },
  }),
};

const ENTITY_LABELS: Record<string, string> = { upi_ids: "UPI IDs", phone_numbers: "Phone numbers", amounts: "Amounts", agencies: "Claimed agencies", banks_apps: "Banks, apps & couriers", links: "Links" };

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const [report, setReport] = useState<StoredReport | null>(null);
  const [missing, setMissing] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => { getReport(params.id).then((value) => value ? setReport(value) : setMissing(true)); }, [params.id]);
  const entityGroups = useMemo(
    () => report
      ? (Object.entries(report.entities) as [keyof Entities, string[]][]).filter(([, values]) => values.length)
      : [],
    [report],
  );
  const animatedRisk = useCountUp(report?.risk_score ?? 0, 950, 220);
  if (!report) return <main className="page-shell loading">{missing ? <div className="empty-state panel"><div className="empty-icon">?</div><h2>Report not found on this device.</h2><p>Reports live only in this browser&apos;s IndexedDB. They are not synced across devices.</p><Link className="button primary" href="/analyze">Run a new analysis</Link></div> : "Loading the local report…"}</main>;

  const current = report;
  const family = FAMILY_META[current.classification.family];
  const safe = current.classification.family === "legitimate";
  const highestStage = current.stages.reduce((best, item) => STAGE_META[item.stage].order > STAGE_META[best].order ? item.stage : best, "s0_none" as keyof typeof STAGE_META);
  const sortedProbabilities = Object.entries(current.classification.all_probs).sort((a, b) => b[1] - a[1]) as [ScamFamily, number][];

  async function copyComplaint() { await navigator.clipboard.writeText(current.complaint.text_en); setCopied(true); window.setTimeout(() => setCopied(false), 1800); }
  async function downloadPdf() {
    await generateComplaintPdf(current);
  }
  async function shareReport() {
    const text = current.actions.sms_body;
    if (navigator.share) await navigator.share({ title: "Digital Inspector alert", text });
    else await navigator.clipboard.writeText(text);
  }

  return <main className="page-shell report-page">
    <div className="report-breadcrumb"><Link href="/dashboard">My reports</Link><span>/</span><span>{current.request_id.slice(0, 8).toUpperCase()}</span><div><Link href="/analyze">New analysis</Link><button onClick={shareReport}>Share report ↗</button></div></div>
    <motion.section animate="show" className={`verdict-hero ${safe ? "safe" : "danger"}`} custom={0} initial="hidden" style={{ "--family": family.color } as React.CSSProperties} variants={reveal}>
      <div className="verdict-copy"><div className="verdict-label"><i />{safe ? "No known scam pattern detected" : "Scam pattern detected"}</div><h1>{family.name}</h1><p>{safe ? "The evidence resembles a legitimate interaction, but remain alert if the caller changes course or asks for credentials, remote access, or payment." : `${family.short}. Stop contact, preserve the evidence, and do not send money or credentials.`}</p><div className="verdict-meta"><span><b>{Math.round(current.classification.confidence * 100)}%</b> family confidence</span><span><b>{STAGE_META[highestStage].name}</b> highest stage</span><span><b>{current.asr_path?.toUpperCase() ?? "TEXT"}</b> input path</span></div>{!current.classification.calibrated && <div className="calibration-note">Confidence is raw model output; calibration artifact is not loaded.</div>}</div>
      <div className="risk-block"><div className="risk-ring" style={{ "--risk": animatedRisk } as React.CSSProperties}><div><strong>{animatedRisk}</strong><span>/ 100</span></div></div><b>{current.risk_score >= 80 ? "Critical risk" : current.risk_score >= 55 ? "High risk" : current.risk_score >= 30 ? "Elevated risk" : "Low risk"}</b><small>Deterministic family × stage × evidence score</small></div>
    </motion.section>

    {!safe && <motion.section animate="show" className="action-command" custom={1} initial="hidden" variants={reveal}><div className="command-icon">!</div><div><span>Golden-hour action</span><h2>{entityGroups.some(([key]) => key === "amounts" || key === "upi_ids") ? "Payment evidence detected. Call 1930 now." : "Preserve this evidence and stop contact."}</h2><p>Never call a number supplied by the suspicious caller. Use the official helpline and bank channels.</p></div><div><a className="button primary" href="tel:1930">Call 1930</a><a className="button light-button" href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">Report online ↗</a></div></motion.section>}

    <motion.div animate="show" className="report-layout" custom={2} initial="hidden" variants={reveal}>
      <div className="report-main">
        <section className="panel report-section"><div className="panel-title"><div><span>Conversation intelligence</span><h2>Playbook timeline</h2></div><small>{current.stages.length} utterances</small></div>{current.stages.every((stage) => stage.confidence === 0) ? <div className="notice">The stage model was unavailable for this analysis.</div> : <div className="rich-timeline">{current.stages.map((stage, index) => { const segment = current.transcript.segments.find((item) => item.id === stage.segment_id); const meta = STAGE_META[stage.stage]; return <article className={stage.stage === "s0_none" ? "benign" : "flagged"} key={`${stage.segment_id}-${index}`}><div className="timeline-rail"><i>{index + 1}</i><span /></div><div><header><b>{meta.name}</b><span>{Math.round(stage.confidence * 100)}%</span></header><p>“{segment?.text}”</p><small>{meta.description}</small></div></article>; })}</div>}</section>
        <section className="panel report-section"><div className="panel-title"><div><span>Verbatim extraction</span><h2>Actionable evidence</h2></div><small>Regex + dictionaries</small></div>{entityGroups.length ? <div className="evidence-groups">{entityGroups.map(([kind, values]) => <div key={kind}><label>{ENTITY_LABELS[kind]}</label><div className="chip-row">{values.map((value) => <button className="chip" title="Copy" onClick={() => navigator.clipboard.writeText(value)} key={value}>{value}<span>⧉</span></button>)}</div></div>)}</div> : <div className="empty-inline">No payment handle, amount, phone number, agency, app, or link was found.</div>}</section>
        <section className="panel report-section"><div className="panel-title"><div><span>Source evidence</span><h2>Transcript</h2></div><small>{current.transcript.text.length.toLocaleString()} characters</small></div><div className="transcript-box">{current.transcript.segments.map((segment) => <p key={segment.id}><span>{current.input_type === "audio" ? `${segment.start.toFixed(1)}s` : String(segment.id + 1).padStart(2, "0")}</span>{segment.text}</p>)}</div></section>
      </div>

      <aside className="report-aside">
        <section className="panel report-section probability-panel"><div className="panel-title"><div><span>Model distribution</span><h2>Family probabilities</h2></div></div>{sortedProbabilities.map(([id, probability]) => <div className="probability-row" key={id}><div><span>{FAMILY_META[id].name}</span><b>{Math.round(probability * 100)}%</b></div><i><span style={{ width: `${probability * 100}%`, background: FAMILY_META[id].color }} /></i></div>)}</section>
        <section className="panel report-section"><div className="panel-title"><div><span>E5 retrieval</span><h2>Closest known scripts</h2></div></div>{current.similar_scripts.length ? <div className="similar-list">{current.similar_scripts.map((script, index) => <article key={script.script_id}><div><i>{index + 1}</i><span style={{ color: FAMILY_META[script.family].color }}>{FAMILY_META[script.family].name}</span><b>{Math.round(script.similarity * 100)}%</b></div><p>{script.excerpt}</p><small>{script.script_id}</small></article>)}</div> : <p className="muted">The similarity index was unavailable for this report.</p>}</section>
        {current.complaint.text_en && <section className="panel report-section complaint-panel"><div className="panel-title"><div><span>Deterministic template</span><h2>Complaint draft</h2></div></div><p>{current.complaint.text_en}</p><div className="stack-actions"><button className="button primary" onClick={downloadPdf}>Download PDF</button><button className="button secondary" onClick={copyComplaint}>{copied ? "Copied ✓" : "Copy for portal"}</button></div></section>}
      </aside>
    </motion.div>
    <div className="report-final-actions"><span>Reference {current.request_id}</span><div><Link href="/dashboard">View local history</Link><Link href="/analyze">Analyze more evidence →</Link></div></div>
  </main>;
}
