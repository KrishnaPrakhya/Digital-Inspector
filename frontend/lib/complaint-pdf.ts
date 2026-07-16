import type { StoredReport } from "@/lib/storage";
import { FAMILY_META, STAGE_META } from "@/lib/scam-content";

const PAGE_WIDTH = 210;
const PAGE_HEIGHT = 297;
const MARGIN = 18;
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2;
const BOTTOM_LIMIT = PAGE_HEIGHT - 24;

const ENTITY_LABELS: Record<string, string> = {
  upi_ids: "UPI handles",
  phone_numbers: "Phone numbers",
  amounts: "Amounts demanded",
  agencies: "Claimed authorities",
  banks_apps: "Banks, apps & couriers",
  links: "Links sent",
};

const DEVANAGARI = /[ऀ-ॿ]/;

function pdfSafe(text: string) {
  return text
    .replace(/₹/g, "Rs ")
    .replace(/→/g, "->")
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/…/g, "...")
    .replace(/[‐-–]/g, "-");
}

function riskLabel(score: number) {
  if (score >= 80) return "Critical";
  if (score >= 55) return "High";
  if (score >= 30) return "Elevated";
  return "Low";
}

export async function generateComplaintPdf(report: StoredReport) {
  const { jsPDF } = await import("jspdf");
  const pdf = new jsPDF({ unit: "mm", format: "a4" });
  const family = FAMILY_META[report.classification.family];
  const generatedAt = new Date().toISOString().replace("T", " ").slice(0, 16) + " UTC";
  let y = 0;

  const drawFooter = () => {
    pdf.setDrawColor(226);
    pdf.setLineWidth(0.2);
    pdf.line(MARGIN, PAGE_HEIGHT - 17, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 17);
    pdf.setFont("helvetica", "normal");
    pdf.setFontSize(7);
    pdf.setTextColor(130);
    pdf.text(`Reference ${report.request_id}`, MARGIN, PAGE_HEIGHT - 12);
    pdf.text(`Page ${pdf.getNumberOfPages()}`, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 12, { align: "right" });
    pdf.text(
      "AI-assisted draft. Review every detail before submission. Not proof of fraud.",
      MARGIN,
      PAGE_HEIGHT - 8,
    );
  };

  const ensure = (needed: number) => {
    if (y + needed > BOTTOM_LIMIT) {
      drawFooter();
      pdf.addPage();
      y = MARGIN + 4;
    }
  };

  const heading = (text: string) => {
    ensure(16);
    y += 4;
    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(8.5);
    pdf.setTextColor(158, 32, 60);
    pdf.text(text.toUpperCase(), MARGIN, y);
    y += 2.2;
    pdf.setDrawColor(226);
    pdf.setLineWidth(0.3);
    pdf.line(MARGIN, y, PAGE_WIDTH - MARGIN, y);
    y += 5.5;
  };

  const body = (text: string, size = 9.5, color = 45) => {
    pdf.setFont("helvetica", "normal");
    pdf.setFontSize(size);
    pdf.setTextColor(color);
    for (const line of pdf.splitTextToSize(pdfSafe(text), CONTENT_WIDTH) as string[]) {
      ensure(6);
      pdf.text(line, MARGIN, y);
      y += size * 0.5;
    }
  };

  const field = (label: string, value: string) => {
    ensure(6);
    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(9);
    pdf.setTextColor(90);
    pdf.text(label, MARGIN, y);
    pdf.setFont("helvetica", "normal");
    pdf.setTextColor(25);
    for (const line of pdf.splitTextToSize(pdfSafe(value), CONTENT_WIDTH - 46) as string[]) {
      pdf.text(line, MARGIN + 46, y);
      y += 4.6;
    }
    y += 0.6;
  };

  pdf.setFillColor(12, 13, 17);
  pdf.rect(0, 0, PAGE_WIDTH, 30, "F");
  pdf.setTextColor(255);
  pdf.setFont("helvetica", "bold");
  pdf.setFontSize(18);
  pdf.text("Digital Inspector", MARGIN, 14);
  pdf.setFont("helvetica", "normal");
  pdf.setFontSize(8.5);
  pdf.setTextColor(190);
  pdf.text("Cybercrime complaint draft — prepared for cybercrime.gov.in", MARGIN, 21);
  pdf.setTextColor(150);
  pdf.setFontSize(7.5);
  pdf.text(generatedAt, PAGE_WIDTH - MARGIN, 14, { align: "right" });
  pdf.text(report.complaint.category || "Not applicable", PAGE_WIDTH - MARGIN, 21, { align: "right" });
  y = 42;

  heading("Case reference");
  field("Reference ID", report.request_id);
  field("Generated", generatedAt);
  field("Portal category", report.complaint.category || "Not applicable");
  field("Evidence type", report.input_type === "audio" ? `Call recording (transcribed via ${(report.asr_path ?? "asr").toUpperCase()})` : "Pasted message or screenshot text");

  heading("Detection summary");
  field("Detected pattern", family.name);
  field(
    "Model confidence",
    `${Math.round(report.classification.confidence * 100)}% ${report.classification.calibrated ? "(temperature-calibrated)" : "(raw model output; calibration not loaded)"}`,
  );
  field("Risk score", `${report.risk_score} / 100 — ${riskLabel(report.risk_score)}`);

  const flagged = report.stages.filter((item) => item.stage !== "s0_none");
  const stageNames = [...new Set(flagged.map((item) => STAGE_META[item.stage].name))];
  field("Playbook stages", stageNames.length ? stageNames.join(" → ") : "No manipulative stage detected");

  heading("Complaint narrative");
  body(
    report.complaint.text_en ||
      "No complaint narrative was generated because no known scam pattern was detected in this evidence.",
    10,
    25,
  );

  const entityGroups = (Object.entries(report.entities) as [string, string[]][]).filter(
    ([, values]) => values.length,
  );

  heading("Extracted evidence");
  if (entityGroups.length) {
    for (const [kind, values] of entityGroups) {
      field(ENTITY_LABELS[kind] ?? kind, values.join(", "));
    }
    y += 1;
    body(
      "Extracted verbatim by deterministic pattern matching and curated dictionaries. No language model produced or altered these values.",
      7.5,
      130,
    );
  } else {
    body("No payment handle, amount, phone number, authority, app, or link was found in this evidence.", 9.5, 90);
  }

  if (flagged.length) {
    heading("Observed playbook progression");
    let index = 0;
    for (const item of flagged.slice(0, 8)) {
      const segment = report.transcript.segments.find((entry) => entry.id === item.segment_id);
      if (!segment) continue;
      index += 1;
      ensure(11);
      pdf.setFont("helvetica", "bold");
      pdf.setFontSize(8.5);
      pdf.setTextColor(158, 32, 60);
      pdf.text(`${index}. ${STAGE_META[item.stage].name}`, MARGIN, y);
      y += 4.2;
      pdf.setFont("helvetica", "italic");
      pdf.setFontSize(8.5);
      pdf.setTextColor(60);
      const quote = DEVANAGARI.test(segment.text)
        ? "[Devanagari utterance - retained verbatim in the app report; this PDF font cannot render it]"
        : `"${segment.text}"`;
      for (const line of pdf.splitTextToSize(pdfSafe(quote), CONTENT_WIDTH - 4) as string[]) {
        ensure(5);
        pdf.text(line, MARGIN + 4, y);
        y += 4.2;
      }
      y += 1.5;
    }
  }

  heading("Recommended actions");
  const actions = [
    "If money has already been transferred, call the cyber-fraud helpline 1930 immediately. Funds reported within the first hours can sometimes be frozen mid-transfer.",
    `File this complaint at ${report.complaint.portal_url || "https://cybercrime.gov.in"} under the category "${report.complaint.category || "Online Financial Fraud"}".`,
    "Contact your bank only through the number printed on your card or its official app. Never call a number supplied by the suspicious caller.",
    "Preserve the original recording, screenshots, and transaction references. Do not delete the conversation.",
    "No genuine police officer, bank, or government agency will ever demand payment to a personal account, request an OTP, or ask you to stay on a video call.",
  ];
  for (const action of actions) {
    ensure(9);
    pdf.setFont("helvetica", "bold");
    pdf.setFontSize(9);
    pdf.setTextColor(158, 32, 60);
    pdf.text("•", MARGIN, y);
    pdf.setFont("helvetica", "normal");
    pdf.setTextColor(45);
    for (const line of pdf.splitTextToSize(action, CONTENT_WIDTH - 5) as string[]) {
      ensure(5);
      pdf.text(line, MARGIN + 4, y);
      y += 4.4;
    }
    y += 1.6;
  }

  heading("Methodology and limitations");
  body(
    "Scam family and playbook stage were classified by two fine-tuned mmBERT-small transformer models running locally through ONNX Runtime. Similar known scripts were retrieved with a multilingual-e5-small embedding index. Speech was transcribed by Whisper. Entity extraction uses deterministic regular expressions and curated dictionaries, and this complaint narrative is assembled from a fixed template — no language model wrote, summarised, or reworded any part of this document, so no detail here can be fabricated.",
    8.5,
    70,
  );
  y += 2;
  body(
    "This report is decision support, not proof that the caller is fraudulent. Speech-recognition errors, code-mixed language, and unfamiliar scam scripts can all affect the result. Verify every extracted value against your own records before submitting, and independently confirm any request using official contact numbers.",
    8.5,
    70,
  );

  drawFooter();
  pdf.save(`digital-inspector-complaint-${report.request_id.slice(0, 8)}.pdf`);
}
