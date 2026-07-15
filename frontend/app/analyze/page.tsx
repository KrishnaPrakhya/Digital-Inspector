"use client";

import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Waveform } from "@/components/Waveform";
import {
  MAX_AUDIO_BYTES,
  MAX_AUDIO_DURATION_SECONDS,
  analyzeAudio,
  analyzeText,
} from "@/lib/api";
import { saveReport } from "@/lib/storage";
import demoManifest from "@/public/demo/manifest.json";

type Mode = "record" | "upload" | "text" | "screenshot";

function audioDuration(file: Blob): Promise<number> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const audio = document.createElement("audio");
    audio.preload = "metadata";
    audio.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      resolve(audio.duration);
    };
    audio.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Could not read the audio file."));
    };
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
  const [ocrProgress, setOcrProgress] = useState<number | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const previewUrl = useMemo(() => file ? URL.createObjectURL(file) : "", [file]);
  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  useEffect(() => {
    if (!recording) return;
    const timer = window.setInterval(() => {
      setSeconds((value) => {
        if (value + 1 >= MAX_AUDIO_DURATION_SECONDS) recorderRef.current?.stop();
        return value + 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [recording]);

  async function acceptAudio(candidate: File) {
    setError("");
    if (candidate.size > MAX_AUDIO_BYTES) throw new Error("Audio must be smaller than 25 MB.");
    const duration = await audioDuration(candidate);
    if (duration > MAX_AUDIO_DURATION_SECONDS + 1) throw new Error("Audio must be 3 minutes or shorter.");
    setFile(candidate);
  }

  async function startRecording() {
    try {
      setError("");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const preferred = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/mp4";
      const recorder = new MediaRecorder(stream, { mimeType: preferred });
      recorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = (event) => event.data.size && chunksRef.current.push(event.data);
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
        const extension = recorder.mimeType.includes("mp4") ? "m4a" : "webm";
        setFile(new File([blob], `recording.${extension}`, { type: recorder.mimeType }));
        setRecording(false);
        streamRef.current?.getTracks().forEach((track) => track.stop());
      };
      setSeconds(0);
      setRecording(true);
      recorder.start(500);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Microphone access failed.");
    }
  }

  async function readScreenshot(candidate: File) {
    setBusy(true);
    setError("");
    setOcrProgress(0);
    try {
      const Tesseract = await import("tesseract.js");
      const result = await Tesseract.recognize(candidate, "eng+hin", {
        logger: (message) => {
          if (typeof message.progress === "number") setOcrProgress(Math.round(message.progress * 100));
        },
      });
      setText(result.data.text.trim());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Screenshot OCR failed.");
    } finally {
      setBusy(false);
      setOcrProgress(null);
    }
  }

  async function completeAnalysis(work: () => ReturnType<typeof analyzeText>) {
    setBusy(true);
    setError("");
    setStep(1);
    const timer = window.setInterval(() => setStep((value) => Math.min(3, value + 1)), 900);
    try {
      const result = await work();
      setStep(3);
      await saveReport(result);
      router.push(`/report/${result.request_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Analysis failed. Check the API connection and try again.");
      setStep(0);
    } finally {
      window.clearInterval(timer);
      setBusy(false);
    }
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
    setMode("upload");
    setError("");
    try {
      const response = await fetch(`/demo/${filename}`);
      const blob = await response.blob();
      const demoFile = new File([blob], filename, { type: blob.type || (filename.endsWith(".wav") ? "audio/wav" : "audio/mpeg") });
      setFile(demoFile);
      await completeAnalysis(() => analyzeAudio(demoFile, filename));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Demo analysis failed.");
    }
  }

  const tabs: [Mode, string][] = [["record", "Record call"], ["upload", "Upload audio"], ["text", "Paste text"], ["screenshot", "Scan screenshot"]];
  return (
    <main className="page-shell">
      <div className="eyebrow"><span /> Evidence analyzer</div>
      <h1 className="page-title">What happened?</h1>
      <p className="muted">Your evidence is sent only to the analysis API. Recordings are not stored in browser history; reports stay in IndexedDB on this device.</p>
      <div className="tabs">{tabs.map(([id, label]) => <button className={`tab ${mode === id ? "active" : ""}`} key={id} onClick={() => { setMode(id); setError(""); }}>{label}</button>)}</div>

      <div className="input-grid">
        <motion.section className="panel" key={mode} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          <div className="dropzone">
            {mode === "record" && <><h2>{recording ? `Recording ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}` : "Record suspicious audio"}</h2><p className="muted">Maximum 3 minutes. Chrome records WebM; Safari may record MP4.</p><button className={`button ${recording ? "secondary" : "primary"}`} onClick={() => recording ? recorderRef.current?.stop() : startRecording()}>{recording ? "Stop recording" : "Use microphone"}</button></>}
            {mode === "upload" && <><h2>Drop in the recording</h2><p className="muted">WebM, OGG, MP4, M4A, WAV or MP3 · 25 MB max</p><input className="file-input" type="file" accept="audio/*,.webm,.ogg,.mp4,.m4a,.wav,.mp3" onChange={(event) => { const chosen = event.target.files?.[0]; if (chosen) acceptAudio(chosen).catch((caught) => setError(caught.message)); }} /></>}
            {mode === "text" && <textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="Paste the SMS, WhatsApp message, or call transcript here…" />}
            {mode === "screenshot" && <><h2>Extract chat text on-device</h2><p className="muted">OCR runs in this browser using English + Hindi recognition.</p><input type="file" accept="image/*" onChange={(event) => { const chosen = event.target.files?.[0]; if (chosen) readScreenshot(chosen); }} />{ocrProgress !== null && <p>Reading image… {ocrProgress}%</p>}{text && <textarea value={text} onChange={(event) => setText(event.target.value)} />}</>}
          </div>
          {previewUrl && <><Waveform url={previewUrl} /><p className="muted">{file?.name} · {file ? (file.size / 1024 / 1024).toFixed(2) : 0} MB</p></>}
          {error && <div className="error">{error}</div>}
          <div className="pipeline"><span className={step > 1 ? "done" : step === 1 ? "active" : ""}>Transcribe</span><span className={step > 2 ? "done" : step === 2 ? "active" : ""}>Classify</span><span className={step === 3 ? "active" : ""}>Extract & prepare</span></div>
          <button className="button primary" disabled={busy || recording} onClick={submit}>{busy ? "Analyzing evidence…" : "Analyze evidence"}</button>
        </motion.section>

        <aside className="panel"><h3>One-click demos</h3><p className="muted">Reenactments are synthetic and labelled. Real samples come from the NCSU robocall dataset.</p><div className="demo-list">{demoManifest.map((demo) => <button className="demo-card" disabled={busy} key={demo.id} onClick={() => runDemo(demo.filename)}><strong>{demo.family?.replaceAll("_", " ") ?? "Real robocall"}</strong><small>{demo.kind === "reenactment" ? "Reenactment" : "Real recording"} · {demo.language.toUpperCase()}</small></button>)}</div></aside>
      </div>
    </main>
  );
}
