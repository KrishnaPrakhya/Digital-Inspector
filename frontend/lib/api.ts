export type InputType = "audio" | "text";
export type AsrPath = "groq" | "local" | null;

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

export const MAX_AUDIO_BYTES = 25 * 1024 * 1024;
export const MAX_AUDIO_DURATION_SECONDS = 180;

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:7860";

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
    const detail = await res.text();
    throw new ApiError(res.status, detail || res.statusText);
  }
  return (await res.json()) as T;
}

export async function analyzeAudio(
  file: Blob,
  filename = "recording.webm",
): Promise<AnalyzeResponse> {
  const formData = new FormData();
  formData.append("audio", file, filename);

  const res = await fetch(`${API_BASE_URL}/api/v1/analyze/audio`, {
    method: "POST",
    body: formData,
  });

  return parseJsonOrThrow<AnalyzeResponse>(res);
}

export async function analyzeText(text: string): Promise<AnalyzeResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/analyze/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });

  return parseJsonOrThrow<AnalyzeResponse>(res);
}

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE_URL}/health`);
  return parseJsonOrThrow<HealthResponse>(res);
}
