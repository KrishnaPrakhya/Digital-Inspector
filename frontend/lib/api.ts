export type InputType = "audio" | "text";
export type AsrPath = "groq" | "local" | null;
export type AnalysisSource = "user" | "demo" | "automated_test";

export type ScamFamily =
  | "digital_arrest"
  | "kyc_bank_fraud"
  | "parcel_courier"
  | "tech_support"
  | "refund_reward"
  | "investment_fraud"
  | "legitimate";

export type PlaybookStage =
  | "s0_none"
  | "s1_authority_claim"
  | "s2_threat_urgency"
  | "s3_isolation"
  | "s4_info_harvest"
  | "s5_payment_demand";

export interface TranscriptSegment {
  id: number;
  start: number;
  end: number;
  text: string;
}

export interface Transcript {
  text: string;
  segments: TranscriptSegment[];
}

export interface Classification {
  family: ScamFamily;
  confidence: number;
  calibrated: boolean;
  all_probs: Record<ScamFamily, number>;
}

export interface StagePrediction {
  segment_id: number;
  stage: PlaybookStage;
  confidence: number;
}

export interface Entities {
  upi_ids: string[];
  phone_numbers: string[];
  amounts: string[];
  agencies: string[];
  banks_apps: string[];
  links: string[];
}

export interface SimilarScript {
  script_id: string;
  family: ScamFamily;
  similarity: number;
  excerpt: string;
}

export interface Complaint {
  text_en: string;
  category: string;
  portal_url: string;
}

export interface Actions {
  helpline: string;
  sms_body: string;
}

export interface AnalyzeResponse {
  request_id: string;
  input_type: InputType;
  asr_path: AsrPath;
  transcript: Transcript;
  classification: Classification;
  stages: StagePrediction[];
  risk_score: number;
  entities: Entities;
  similar_scripts: SimilarScript[];
  complaint: Complaint;
  actions: Actions;
}

export interface HealthResponse {
  status: string;
  models: {
    family: boolean;
    stage: boolean;
    embedder: boolean;
  };
  asr: {
    groq_configured: boolean;
    local_loaded: boolean;
  };
  version: string;
}

export interface PulseResponse {
  available: boolean;
  window_days?: number;
  totals?: {
    analyses: number;
    scams: number;
    high_risk: number;
    avg_risk: number;
  };
  families?: { family: string; count: number }[];
  stages?: { stage: string; count: number }[];
  languages?: { language: string; count: number }[];
  evidence?: { kind: string; count: number }[];
  daily?: { day: string; scams: number }[];
}

export const MAX_AUDIO_BYTES = 25 * 1024 * 1024;
export const MAX_AUDIO_DURATION_SECONDS = 180;

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:7860";
const REQUEST_TIMEOUT_MS = 120_000;

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseJsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const raw = await res.text();
    let detail = raw;
    try {
      const parsed = JSON.parse(raw) as { detail?: string };
      detail = parsed.detail ?? raw;
    } catch {}
    throw new ApiError(res.status, detail || res.statusText);
  }
  return (await res.json()) as T;
}

async function apiFetch(path: string, init?: RequestInit) {
  try {
    return await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: init?.signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new ApiError(408, "The analysis took too long. The model service may be waking up; please retry.");
    }
    throw new ApiError(0, "Cannot reach the analysis service. Check the connection and try again.");
  }
}

export async function analyzeAudio(
  file: Blob,
  filename = "recording.webm",
  source: AnalysisSource = "user",
): Promise<AnalyzeResponse> {
  const formData = new FormData();
  formData.append("audio", file, filename);

  const res = await apiFetch("/api/v1/analyze/audio", {
    method: "POST",
    headers: { "X-Analysis-Source": source },
    body: formData,
  });

  return parseJsonOrThrow<AnalyzeResponse>(res);
}

export async function analyzeText(
  text: string,
  source: AnalysisSource = "user",
): Promise<AnalyzeResponse> {
  const res = await apiFetch("/api/v1/analyze/text", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Analysis-Source": source,
    },
    body: JSON.stringify({ text }),
  });

  return parseJsonOrThrow<AnalyzeResponse>(res);
}

export async function getHealth(): Promise<HealthResponse> {
  const res = await apiFetch("/health", { signal: AbortSignal.timeout(8_000) });
  return parseJsonOrThrow<HealthResponse>(res);
}

export async function searchSimilarScripts(query: string, limit = 6): Promise<SimilarScript[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const res = await apiFetch(`/api/v1/similar?${params}`);
  return parseJsonOrThrow<SimilarScript[]>(res);
}

export async function getThreatPulse(days = 7): Promise<PulseResponse> {
  const res = await apiFetch(`/api/v1/pulse?days=${days}`, { signal: AbortSignal.timeout(10_000) });
  return parseJsonOrThrow<PulseResponse>(res);
}
