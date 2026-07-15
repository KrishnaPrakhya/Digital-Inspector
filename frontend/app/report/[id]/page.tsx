"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import type { AnalyzeResponse, PlaybookStage, ScamFamily } from "@/lib/api";
import { getReport } from "@/lib/storage";

const FAMILY_NAMES: Record<ScamFamily, string> = {
  digital_arrest: "Digital arrest scam",
  kyc_bank_fraud: "KYC / bank fraud",
  parcel_courier: "Parcel / courier scam",
  tech_support: "Tech-support scam",
  refund_reward: "Refund / reward scam",
  investment_fraud: "Investment fraud",
  legitimate: "No known scam pattern",
};
const STAGE_NAMES: Record<PlaybookStage, string> = {
  s0_none: "No scam behavior",
  s1_authority_claim: "Authority claim",
  s2_threat_urgency: "Threat and urgency",
  s3_isolation: "Isolation and secrecy",
  s4_info_harvest: "Information harvesting",
  s5_payment_demand: "Payment demand",
};

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const [report, setReport] = useState<AnalyzeResponse | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    getReport(params.id).then((value) => value ? setReport(value) : setMissing(true));
  }, [params.id]);

  const chips = useMemo(
    () => report
      ? (Object.entries(report.entities) as [string, string[]][]).flatMap(([kind, values]) => values.map((value) => ({ kind, value })))
      : [],
    [report],
  );

  if (!report) return <main className="page-shell loading">{missing ? "This report is not stored on this device. Run a new analysis first." : "Loading report…"}</main>;

  const currentReport = report;
  const safe = report.classification.family === "legitimate";
  async function downloadPdf() {
    const { jsPDF } = await import("jspdf");
    const pdf = new jsPDF();
    pdf.setFontSize(18); pdf.text("Digital Inspector — Complaint Draft", 18, 20);
    pdf.setFontSize(10); pdf.text(`Reference: ${currentReport.request_id}`, 18, 29);
    pdf.setFontSize(12); pdf.text(pdf.splitTextToSize(currentReport.complaint.text_en || "No complaint generated for a legitimate call.", 174), 18, 42);
    pdf.save(`digital-inspector-${currentReport.request_id.slice(0, 8)}.pdf`);
  }

  return (
    <main className="page-shell">
      <div className="eyebrow"><span /> Analysis report</div>
      <p className="muted">Reference {report.request_id}</p>
      <div className="report-top">
        <section className={`panel verdict ${safe ? "safe" : ""}`}><div className="verdict-label">{safe ? "No known scam pattern" : "Scam pattern detected"}</div><h1>{FAMILY_NAMES[report.classification.family]}</h1><p className="confidence">{(report.classification.confidence * 100).toFixed(1)}% confidence · {report.classification.calibrated ? "temperature calibrated" : "uncalibrated model output"} · {report.asr_path ? `${report.asr_path} ASR` : "text input"}</p><p className="muted">{safe ? "Remain cautious if the caller asks for OTPs, remote access, or payment." : "Do not transfer money or share credentials. Preserve the evidence and report quickly."}</p></section>
        <section className="panel"><div className="risk-ring" style={{ "--risk": report.risk_score } as React.CSSProperties}><strong>{report.risk_score}</strong></div><p className="muted" style={{ textAlign: "center" }}>Risk score / 100</p></section>
      </div>

      <div className="report-grid">
        <section className="panel"><h2>Playbook timeline</h2>{report.stages.every((stage) => stage.confidence === 0) && <p className="muted">The stage model is not loaded yet; family detection remains active.</p>}<div className="timeline">{report.stages.map((stage) => { const segment = report.transcript.segments.find((item) => item.id === stage.segment_id); return <div className="timeline-item" key={stage.segment_id}><i className="timeline-dot" /><div><strong>{STAGE_NAMES[stage.stage]}</strong><p>{segment?.text}</p>{stage.confidence > 0 && <small className="muted">{(stage.confidence * 100).toFixed(0)}% confidence</small>}</div></div>; })}</div></section>
        <section className="panel"><h2>Extracted evidence</h2>{chips.length ? <div className="chip-row">{chips.map((chip) => <span className="chip" title={chip.kind} key={`${chip.kind}-${chip.value}`}>{chip.value}</span>)}</div> : <p className="muted">No payment handles, phone numbers, amounts, agencies, apps, or links were extracted.</p>}<h3>Closest known scripts</h3>{report.similar_scripts.length ? report.similar_scripts.map((script) => <p key={script.script_id}><strong>{(script.similarity * 100).toFixed(0)}% · {FAMILY_NAMES[script.family]}</strong><br /><span className="muted">{script.excerpt}</span></p>) : <p className="muted">Similarity index is not loaded yet.</p>}</section>
        <section className="panel wide"><h2>Act now</h2><div className="action-row"><a className="button primary" href="tel:1930">Call 1930</a><button className="button secondary" onClick={downloadPdf} disabled={!report.complaint.text_en}>Download complaint PDF</button><button className="button secondary" onClick={() => navigator.clipboard.writeText(report.complaint.text_en)} disabled={!report.complaint.text_en}>Copy for portal</button><a className="button secondary" href={`sms:?&body=${encodeURIComponent(report.actions.sms_body)}`}>Share by SMS</a><a className="button secondary" href={report.complaint.portal_url} target="_blank" rel="noreferrer">Open cybercrime.gov.in</a></div>{report.complaint.text_en && <div className="complaint" style={{ marginTop: 18 }}>{report.complaint.text_en}</div>}</section>
        <section className="panel wide"><h2>Transcript</h2><div className="complaint">{report.transcript.text}</div></section>
      </div>
    </main>
  );
}
