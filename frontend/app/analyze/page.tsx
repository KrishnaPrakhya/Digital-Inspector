"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Waveform } from "@/components/Waveform";
import { MAX_AUDIO_BYTES, MAX_AUDIO_DURATION_SECONDS, analyzeAudio, analyzeText, type AnalyzeResponse } from "@/lib/api";
import { FAMILY_META } from "@/lib/scam-content";
import { saveReport } from "@/lib/storage";
import demoManifest from "@/public/demo/manifest.json";

type Mode = "record" | "upload" | "text" | "screenshot";
const TEXT_SAMPLES = [
  { family: "digital_arrest" as const, text: "I am Inspector Sharma from Mumbai Police. If you disconnect, an arrest warrant will be issued today. Do not tell your family or bank. Share your Aadhaar and OTP. Transfer Rs. 50,000 to safe@ybl immediately." },
  { family: "kyc_bank_fraud" as const, text: "This is an SBI KYC officer. Your account will be blocked tonight. Share the OTP and card number now to complete KYC." },
  { family: "legitimate" as const, text: "Hello, this is Meera from the SBI MG Road branch confirming your appointment tomorrow. Please visit the branch. We will never ask for an OTP or payment." },
];

function audioDuration(file: Blob): Promise<number> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file); const audio = document.createElement("audio"); audio.preload = "metadata";
    audio.onloadedmetadata = () => { URL.revokeObjectURL(url); resolve(audio.duration); };
    audio.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Could not read this audio file.")); };
    audio.src = url;
  });
}

export default function AnalyzePage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("record");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [ocrProgress, setOcrProgress] = useState<number | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const previewUrl = useMemo(() => file ? URL.createObjectURL(file) : "", [file]);

  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);
  useEffect(() => () => streamRef.current?.getTracks().forEach((track) => track.stop()), []);
  useEffect(() => {
    if (!recording) return;
    const timer = window.setInterval(() => setSeconds((value) => { if (value + 1 >= MAX_AUDIO_DURATION_SECONDS) recorderRef.current?.stop(); return value + 1; }), 1000);
    return () => window.clearInterval(timer);
  }, [recording]);

  function switchMode(next: Mode) { setMode(next); setError(""); setStep(0); }
  async function acceptAudio(candidate: File) {
    setError("");
    if (candidate.size > MAX_AUDIO_BYTES) throw new Error("Audio must be smaller than 25 MB.");
    const duration = await audioDuration(candidate);
    if (!Number.isFinite(duration) || duration > MAX_AUDIO_DURATION_SECONDS + 1) throw new Error("Audio must be 3 minutes or shorter.");
    setFile(candidate);
  }

  async function startRecording() {
    try {
      setError("");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      streamRef.current = stream;
      const mimeType = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"].find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder; chunksRef.current = [];
      recorder.ondataavailable = (event) => event.data.size && chunksRef.current.push(event.data);
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
        const extension = recorder.mimeType.includes("mp4") ? "m4a" : "webm";
        setFile(new File([blob], `recording.${extension}`, { type: recorder.mimeType })); setRecording(false);
        streamRef.current?.getTracks().forEach((track) => track.stop());
      };
      setSeconds(0); setRecording(true); recorder.start(500);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Microphone access failed."); }
  }

  async function readScreenshot(candidate: File) {
    setBusy(true); setError(""); setOcrProgress(0);
    try {
      const Tesseract = await import("tesseract.js");
      const result = await Tesseract.recognize(candidate, "eng+hin", { logger: (message) => typeof message.progress === "number" && setOcrProgress(Math.round(message.progress * 100)) });
      setText(result.data.text.trim());
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Screenshot OCR failed."); }
    finally { setBusy(false); setOcrProgress(null); }
  }

  async function completeAnalysis(work: () => Promise<AnalyzeResponse>) {
    setBusy(true); setError(""); setStep(1);
    const timer = window.setInterval(() => setStep((value) => Math.min(3, value + 1)), 1100);
    try { const result = await work(); setStep(3); await saveReport(result); router.push(`/report/${result.request_id}`); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Analysis failed. Please retry."); setStep(0); }
    finally { window.clearInterval(timer); setBusy(false); }
  }

  function submit() {
    if (mode === "text" || mode === "screenshot") {
      if (!text.trim()) return setError("Add some text to analyze first.");
      return completeAnalysis(() => analyzeText(text.trim()));
    }
    if (!file) return setError("Record or select an audio file first.");
    return completeAnalysis(() => analyzeAudio(file, file.name));
  }

  async function runDemo(filename: string) {
    switchMode("upload");
    try { const response = await fetch(`/demo/${filename}`); if (!response.ok) throw new Error("Demo file unavailable."); const blob = await response.blob(); const demoFile = new File([blob], filename, { type: blob.type || (filename.endsWith(".wav") ? "audio/wav" : "audio/mpeg") }); setFile(demoFile); await completeAnalysis(() => analyzeAudio(demoFile, filename)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Demo analysis failed."); }
  }

  const tabs: [Mode, string, string][] = [["record", "Record", "Live microphone"], ["upload", "Upload", "Audio file"], ["text", "Paste", "Message or transcript"], ["screenshot", "Screenshot", "On-device OCR"]];
  const canSubmit = (mode === "text" || mode === "screenshot") ? Boolean(text.trim()) : Boolean(file);

  return <main className="page-shell analyze-page">
    <div className="page-intro"><div><div className="eyebrow"><span /> Evidence analyzer</div><h1 className="page-title">Bring the evidence.<br />We&apos;ll trace the pressure.</h1></div><p>Analyze up to three minutes of audio, pasted messages, or a screenshot. The report identifies the scam family, maps each playbook stage, extracts payment evidence, and prepares the next action.</p></div>
    <div className="privacy-ribbon"><span>◉</span><div><b>Privacy by design</b><small>Audio is analyzed, not added to history. Only the structured report is saved locally in this browser.</small></div><span>3 AI models ready</span></div>
    <div className="mode-tabs" role="tablist">{tabs.map(([id, label, hint]) => <button role="tab" aria-selected={mode === id} className={mode === id ? "active" : ""} key={id} onClick={() => switchMode(id)}><b>{label}</b><small>{hint}</small></button>)}</div>

    <div className="input-grid analyzer-grid">
      <motion.section className="panel analyzer-panel" key={mode} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        {mode === "record" && <div className={`capture-zone ${recording ? "recording" : ""}`}><div className="capture-icon"><span className="mic-core">●</span>{recording && <><i /><i /><i /></>}</div><h2>{recording ? `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}` : "Record suspicious audio"}</h2><p>{recording ? "Keep the call audible. Recording stops automatically at 3:00." : "Use speakerphone or play a saved voice note near your microphone."}</p><button className={`button ${recording ? "danger-button" : "primary"}`} onClick={() => recording ? recorderRef.current?.stop() : startRecording()}>{recording ? "■ Stop recording" : "● Start recording"}</button></div>}
        {mode === "upload" && <div className={`capture-zone ${dragging ? "dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); const chosen = event.dataTransfer.files[0]; if (chosen) acceptAudio(chosen).catch((caught) => setError(caught.message)); }}><div className="capture-icon">↑</div><h2>Drop the recording here</h2><p>WebM, OGG, MP4, M4A, WAV or MP3 · 25 MB · 3 minutes</p><label className="button secondary" htmlFor="audio-upload">Choose audio file</label><input id="audio-upload" hidden type="file" accept="audio/*,.webm,.ogg,.mp4,.m4a,.wav,.mp3" onChange={(event) => { const chosen = event.target.files?.[0]; if (chosen) acceptAudio(chosen).catch((caught) => setError(caught.message)); }} /></div>}
        {mode === "text" && <div className="text-entry"><label htmlFor="evidence-text">Message or call transcript</label><textarea id="evidence-text" value={text} onChange={(event) => setText(event.target.value)} placeholder="Paste exactly what the caller or sender said…" maxLength={50_000} /><div className="text-meta"><span>{text.length.toLocaleString()} / 50,000</span><span>English · हिंदी · Hinglish</span></div><div className="sample-chips"><span>Try a verified sample:</span>{TEXT_SAMPLES.map((sample) => <button key={sample.family} onClick={() => setText(sample.text)} style={{ "--sample": FAMILY_META[sample.family].color } as React.CSSProperties}>{FAMILY_META[sample.family].name}</button>)}</div></div>}
        {mode === "screenshot" && <div className="capture-zone"><div className="capture-icon">▣</div><h2>Scan a chat screenshot</h2><p>English and Hindi OCR runs on this device before extracted text is sent for analysis.</p><label className="button secondary" htmlFor="image-upload">Choose screenshot</label><input id="image-upload" hidden type="file" accept="image/*" onChange={(event) => { const chosen = event.target.files?.[0]; if (chosen) readScreenshot(chosen); }} />{ocrProgress !== null && <div className="ocr-progress"><i style={{ width: `${ocrProgress}%` }} /><span>Reading image {ocrProgress}%</span></div>}{text && <textarea className="ocr-text" value={text} onChange={(event) => setText(event.target.value)} />}</div>}

        {previewUrl && <div className="audio-preview"><Waveform url={previewUrl} /><div><span><b>{file?.name}</b><small>{file ? (file.size / 1024 / 1024).toFixed(2) : 0} MB</small></span><button aria-label="Remove audio" onClick={() => setFile(null)}>×</button></div></div>}
        <AnimatePresence>{error && <motion.div className="error" role="alert" aria-live="assertive" initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>{error}</motion.div>}</AnimatePresence>
        <div className="pipeline" aria-live="polite"><span className={step > 1 ? "done" : step === 1 ? "active" : ""}><i>1</i><b>Transcribe</b><small>Speech to text</small></span><span className={step > 2 ? "done" : step === 2 ? "active" : ""}><i>2</i><b>Classify</b><small>Family + stages</small></span><span className={step === 3 ? "active" : ""}><i>3</i><b>Prepare</b><small>Evidence + action</small></span></div>
        <button className="button primary analyze-submit" disabled={busy || recording || !canSubmit} onClick={submit}>{busy ? <><span className="spinner" /> Analyzing evidence…</> : <>Run three-model analysis <span>→</span></>}</button>
      </motion.section>

      <aside className="analyzer-aside"><section className="panel"><div className="panel-title"><div><span>Judge-ready</span><h3>One-click audio demos</h3></div></div><p className="muted">Reenactments are clearly synthetic. Real samples are captured robocalls from the NCSU dataset.</p><div className="demo-list">{demoManifest.map((demo) => <button className="demo-card" disabled={busy} key={demo.id} onClick={() => runDemo(demo.filename)}><span className={`demo-kind ${demo.kind === "real_recording" ? "real" : ""}`}>{demo.kind === "reenactment" ? "R" : "REAL"}</span><div><strong>{demo.family ? FAMILY_META[demo.family as keyof typeof FAMILY_META].name : "Captured robocall"}</strong><small>{demo.kind === "reenactment" ? "Synthetic reenactment" : "Research dataset audio"} · {demo.language.toUpperCase()}</small></div><span>▶</span></button>)}</div></section><section className="panel safety-note"><span>!</span><div><b>If money has moved</b><p>Stop analysis and call 1930 first. Notify the bank through its official number.</p><a href="tel:1930">Call 1930 →</a></div></section></aside>
    </div>
  </main>;
}
