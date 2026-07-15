import { openDB } from "idb";

import type { AnalyzeResponse } from "@/lib/api";

const DB_NAME = "digital-inspector";
const STORE_NAME = "reports";

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
  await db.put(STORE_NAME, report);
}

export async function getReport(id: string): Promise<AnalyzeResponse | undefined> {
  const db = await database();
  return db.get(STORE_NAME, id);
}

