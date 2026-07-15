export type LandscapeMetric = "cases" | "change" | "origins";

export interface StateCyberSignal {
  cases2021: number;
  cases2022: number;
  cases2023: number;
  originHubs?: string[];
}

export const ALL_INDIA_CASES_2023 = 86_420;

export const STATE_CYBER_SIGNALS: Record<string, StateCyberSignal> = {
  "Andaman and Nicobar Islands": { cases2021: 8, cases2022: 28, cases2023: 47 },
  "Andhra Pradesh": { cases2021: 1875, cases2022: 2341, cases2023: 2341 },
  "Arunachal Pradesh": { cases2021: 47, cases2022: 14, cases2023: 24 },
  Assam: { cases2021: 4846, cases2022: 1733, cases2023: 909 },
  Bihar: { cases2021: 1413, cases2022: 1621, cases2023: 4450, originHubs: ["Nawada", "Nalanda", "Patna", "Sheikhpura"] },
  Chandigarh: { cases2021: 15, cases2022: 27, cases2023: 23 },
  Chhattisgarh: { cases2021: 352, cases2022: 439, cases2023: 473 },
  "Dadra and Nagar Haveli and Daman and Diu": { cases2021: 5, cases2022: 5, cases2023: 6 },
  Delhi: { cases2021: 356, cases2022: 685, cases2023: 407, originHubs: ["West Delhi", "North West Delhi", "South West Delhi"] },
  Goa: { cases2021: 36, cases2022: 90, cases2023: 86 },
  Gujarat: { cases2021: 1536, cases2022: 1417, cases2023: 1995 },
  Haryana: { cases2021: 622, cases2022: 681, cases2023: 751, originHubs: ["Nuh"] },
  "Himachal Pradesh": { cases2021: 70, cases2022: 77, cases2023: 127 },
  "Jammu and Kashmir": { cases2021: 154, cases2022: 173, cases2023: 185 },
  Jharkhand: { cases2021: 953, cases2022: 967, cases2023: 1079, originHubs: ["Deoghar", "Jamtara", "Dumka"] },
  Karnataka: { cases2021: 8136, cases2022: 12556, cases2023: 21889, originHubs: ["Bengaluru Urban"] },
  Kerala: { cases2021: 626, cases2022: 773, cases2023: 3295 },
  Ladakh: { cases2021: 5, cases2022: 3, cases2023: 1 },
  Lakshadweep: { cases2021: 1, cases2022: 1, cases2023: 1 },
  "Madhya Pradesh": { cases2021: 589, cases2022: 826, cases2023: 685 },
  Maharashtra: { cases2021: 5562, cases2022: 8249, cases2023: 8103 },
  Manipur: { cases2021: 67, cases2022: 18, cases2023: 3 },
  Meghalaya: { cases2021: 107, cases2022: 75, cases2023: 64 },
  Mizoram: { cases2021: 30, cases2022: 1, cases2023: 31 },
  Nagaland: { cases2021: 8, cases2022: 4, cases2023: 2 },
  Odisha: { cases2021: 2037, cases2022: 1983, cases2023: 2348 },
  Puducherry: { cases2021: 0, cases2022: 64, cases2023: 147 },
  Punjab: { cases2021: 551, cases2022: 697, cases2023: 511 },
  Rajasthan: { cases2021: 1504, cases2022: 1833, cases2023: 2435, originHubs: ["Deeg", "Alwar", "Jaipur", "Khairthal-Tijara"] },
  Sikkim: { cases2021: 0, cases2022: 26, cases2023: 12 },
  "Tamil Nadu": { cases2021: 1076, cases2022: 2082, cases2023: 4121 },
  Telangana: { cases2021: 10303, cases2022: 15297, cases2023: 18236 },
  Tripura: { cases2021: 24, cases2022: 30, cases2023: 36 },
  "Uttar Pradesh": { cases2021: 8829, cases2022: 10117, cases2023: 10794, originHubs: ["Mathura", "Gautam Budh Nagar"] },
  Uttarakhand: { cases2021: 718, cases2022: 559, cases2023: 494 },
  "West Bengal": { cases2021: 513, cases2022: 401, cases2023: 309, originHubs: ["North 24 Parganas", "Kolkata"] },
};

export function percentChange(signal: StateCyberSignal) {
  if (!signal.cases2021) return null;
  return ((signal.cases2023 - signal.cases2021) / signal.cases2021) * 100;
}
