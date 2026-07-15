import type { PlaybookStage, ScamFamily } from "@/lib/api";

export const FAMILY_META: Record<ScamFamily, { name: string; short: string; color: string; icon: string }> = {
  digital_arrest: { name: "Digital arrest", short: "Fake police or agency accusations", color: "#fb7185", icon: "shield" },
  kyc_bank_fraud: { name: "KYC / bank fraud", short: "Account-block and credential phishing", color: "#f59e0b", icon: "bank" },
  parcel_courier: { name: "Parcel / courier", short: "Illegal parcel and customs threats", color: "#a78bfa", icon: "parcel" },
  tech_support: { name: "Tech support", short: "Remote-access and virus deception", color: "#38bdf8", icon: "desktop" },
  refund_reward: { name: "Refund / reward", short: "Prize, cashback and refund traps", color: "#34d399", icon: "gift" },
  investment_fraud: { name: "Investment fraud", short: "Guaranteed-return and task schemes", color: "#f472b6", icon: "chart" },
  legitimate: { name: "No known scam", short: "No known scam pattern detected", color: "#22c55e", icon: "check" },
};

export const STAGE_META: Record<PlaybookStage, { name: string; description: string; order: number }> = {
  s0_none: { name: "No scam behavior", description: "No manipulative playbook signal in this utterance.", order: 0 },
  s1_authority_claim: { name: "Authority claim", description: "Impersonates police, a bank, courier, or government office.", order: 1 },
  s2_threat_urgency: { name: "Threat & urgency", description: "Creates panic through arrest, blocking, or deadline threats.", order: 2 },
  s3_isolation: { name: "Isolation", description: "Demands secrecy or keeps the victim on the line.", order: 3 },
  s4_info_harvest: { name: "Information harvest", description: "Requests OTP, Aadhaar, card, or account details.", order: 4 },
  s5_payment_demand: { name: "Payment demand", description: "Demands UPI, bank, crypto, gift-card, or safe-account payment.", order: 5 },
};

export const PLAYBOOKS = [
  { family: "digital_arrest" as const, signs: ["Video-call police impersonation", "Money-laundering or Aadhaar accusation", "Stay on the line / tell nobody", "Safe-account transfer"], example: "Your Aadhaar is linked to a crime. Stay on video and transfer funds for verification." },
  { family: "kyc_bank_fraud" as const, signs: ["KYC expires today", "Account or card will be blocked", "OTP or card request", "Unverified link or app"], example: "Your SBI KYC expires tonight. Share the OTP now to prevent blocking." },
  { family: "parcel_courier" as const, signs: ["Drugs in a parcel", "Fake customs transfer", "Police escalation", "Clearance or settlement fee"], example: "A parcel in your name contains narcotics. Pay customs clearance immediately." },
  { family: "tech_support" as const, signs: ["Unexpected virus alert", "Install AnyDesk / TeamViewer", "Remote-control request", "Refund processing fee"], example: "Your computer is compromised. Install AnyDesk so our support officer can fix it." },
  { family: "refund_reward" as const, signs: ["Unexpected prize or cashback", "Small fee to release reward", "UPI collect request", "Time-limited claim"], example: "You won a cashback reward. Approve this UPI request to receive it." },
  { family: "investment_fraud" as const, signs: ["Guaranteed returns", "WhatsApp trading group", "Task or rating income", "Withdrawal fee"], example: "Earn guaranteed daily profit. Deposit now to unlock premium tasks." },
];
