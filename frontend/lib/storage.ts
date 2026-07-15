import { openDB } from "idb";

import type { AnalyzeResponse } from "@/lib/api";

const DB_NAME = "digital-inspector";
const STORE_NAME = "reports";

export type StoredReport = AnalyzeResponse & { saved_at?: string };

async function database() {
  return openDB(DB_NAME, 1, {
    upgrade(db) {
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "request_id" });
      }
    },
  });
}

export async function saveReport(report: AnalyzeResponse) {
  const db = await database();
  await db.put(STORE_NAME, { ...report, saved_at: new Date().toISOString() });
}

export async function getReport(id: string): Promise<StoredReport | undefined> {
  const db = await database();
  return db.get(STORE_NAME, id);
}

export async function listReports(): Promise<StoredReport[]> {
  const db = await database();
  const reports = await db.getAll(STORE_NAME) as StoredReport[];
  return reports.sort((a, b) => (b.saved_at ?? "").localeCompare(a.saved_at ?? ""));
}

export async function deleteReport(id: string) {
  const db = await database();
  await db.delete(STORE_NAME, id);
}

export async function clearReports() {
  const db = await database();
  await db.clear(STORE_NAME);
}
