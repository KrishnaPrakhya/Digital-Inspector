"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { FAMILY_META } from "@/lib/scam-content";
import {
  clearReports,
  deleteReport,
  listReports,
  type StoredReport,
} from "@/lib/storage";

export default function DashboardPage() {
  const [reports, setReports] = useState<StoredReport[]>([]);
  const [loaded, setLoaded] = useState(false);
  const refresh = () =>
    listReports().then((value) => {
      setReports(value);
      setLoaded(true);
    });
  useEffect(() => {
    refresh();
  }, []);

  const familyData = useMemo(
    () =>
      Object.entries(
        reports.reduce<Record<string, number>>((acc, report) => {
          const key = report.classification.family;
          acc[key] = (acc[key] ?? 0) + 1;
          return acc;
        }, {}),
      ).map(([family, value]) => ({
        family,
        name: FAMILY_META[family as keyof typeof FAMILY_META].name,
        value,
      })),
    [reports],
  );
  const trendData = useMemo(
    () =>
      [...reports].reverse().map((report, index) => ({
        index: index + 1,
        risk: report.risk_score,
        name: report.saved_at
          ? new Date(report.saved_at).toLocaleDateString()
          : `#${index + 1}`,
      })),
    [reports],
  );
  const highRisk = reports.filter((report) => report.risk_score >= 70).length;
  const scams = reports.filter(
    (report) => report.classification.family !== "legitimate",
  ).length;

  function exportCsv() {
    const header = [
      "request_id",
      "saved_at",
      "input_type",
      "family",
      "confidence",
      "risk_score",
      "asr_path",
    ];
    const lines = reports.map((report) =>
      [
        report.request_id,
        report.saved_at ?? "",
        report.input_type,
        report.classification.family,
        report.classification.confidence,
        report.risk_score,
        report.asr_path ?? "",
      ]
        .map((value) => `"${String(value).replaceAll('"', '""')}"`)
        .join(","),
    );
    const url = URL.createObjectURL(
      new Blob([[header.join(","), ...lines].join("\n")], { type: "text/csv" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "digital-inspector-reports.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  if (!loaded)
    return (
      <main className="page-shell loading">
        Opening your private report history…
      </main>
    );
  return (
    <main className="page-shell dashboard-page">
      <div className="page-intro">
        <div>
          <div className="eyebrow">
            <span /> Private on-device history
          </div>
          <h1 className="page-title">Your local safety dashboard.</h1>
        </div>
        <div className="action-row">
          <button
            className="button secondary"
            disabled={!reports.length}
            onClick={exportCsv}
          >
            Export CSV
          </button>
          <button
            className="button danger-button"
            disabled={!reports.length}
            onClick={async () => {
              if (window.confirm("Delete every locally stored report?")) {
                await clearReports();
                refresh();
              }
            }}
          >
            Clear history
          </button>
        </div>
      </div>
      {!reports.length ? (
        <section className="empty-state panel">
          <div className="empty-icon">◎</div>
          <h2>No reports on this device yet.</h2>
          <p>
            Analyses are stored privately in this browser using IndexedDB. They
            do not sync to an account or cloud dashboard.
          </p>
          <Link className="button primary" href="/analyze">
            Run your first analysis
          </Link>
        </section>
      ) : (
        <>
          <section className="metric-grid">
            <article>
              <span>Total analyses</span>
              <strong>{reports.length}</strong>
              <small>Stored only on this device</small>
            </article>
            <article>
              <span>Scam patterns</span>
              <strong>{scams}</strong>
              <small>
                {Math.round((scams / reports.length) * 100)}% of analyzed
                evidence
              </small>
            </article>
            <article>
              <span>High risk</span>
              <strong>{highRisk}</strong>
              <small>Risk score 70 or higher</small>
            </article>
            <article>
              <span>Average risk</span>
              <strong>
                {Math.round(
                  reports.reduce((sum, report) => sum + report.risk_score, 0) /
                    reports.length,
                )}
              </strong>
              <small>Across local history</small>
            </article>
          </section>
          <section className="dashboard-grid">
            <article className="panel chart-panel">
              <div className="panel-title">
                <div>
                  <span>Distribution</span>
                  <h2>Detected families</h2>
                </div>
              </div>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={familyData}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={66}
                      outerRadius={98}
                      paddingAngle={3}
                    >
                      {familyData.map((entry) => (
                        <Cell
                          fill={
                            FAMILY_META[
                              entry.family as keyof typeof FAMILY_META
                            ].color
                          }
                          key={entry.family}
                        />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        background: "#15171c",
                        border: "1px solid #292c34",
                        borderRadius: 10,
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="legend-list">
                {familyData.map((entry) => (
                  <span key={entry.family}>
                    <i
                      style={{
                        background:
                          FAMILY_META[entry.family as keyof typeof FAMILY_META]
                            .color,
                      }}
                    />
                    {entry.name}
                    <b>{entry.value}</b>
                  </span>
                ))}
              </div>
            </article>
            <article className="panel chart-panel">
              <div className="panel-title">
                <div>
                  <span>History</span>
                  <h2>Risk over time</h2>
                </div>
              </div>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={trendData}
                    margin={{ top: 10, right: 15, bottom: 0, left: -25 }}
                  >
                    <XAxis dataKey="name" stroke="#71717a" fontSize={11} />
                    <YAxis domain={[0, 100]} stroke="#71717a" fontSize={11} />
                    <Tooltip
                      contentStyle={{
                        background: "#15171c",
                        border: "1px solid #292c34",
                        borderRadius: 10,
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="risk"
                      stroke="#fb7185"
                      strokeWidth={3}
                      dot={{ fill: "#fb7185", r: 4 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </article>
          </section>
          <section className="report-list panel">
            <div className="panel-title">
              <div>
                <span>Evidence log</span>
                <h2>Recent reports</h2>
              </div>
              <small>{reports.length} saved</small>
            </div>
            <div className="report-table">
              <div className="report-row header">
                <span>Verdict</span>
                <span>Risk</span>
                <span>Input</span>
                <span>Saved</span>
                <span />
              </div>
              {reports.map((report) => {
                const meta = FAMILY_META[report.classification.family];
                return (
                  <div className="report-row" key={report.request_id}>
                    <Link href={`/report/${report.request_id}`}>
                      <i style={{ background: meta.color }} />
                      <div>
                        <b>{meta.name}</b>
                        <small>
                          {Math.round(report.classification.confidence * 100)}%
                          confidence
                        </small>
                      </div>
                    </Link>
                    <strong
                      className={report.risk_score >= 70 ? "high-risk" : ""}
                    >
                      {report.risk_score}
                    </strong>
                    <span>{report.input_type}</span>
                    <span>
                      {report.saved_at
                        ? new Date(report.saved_at).toLocaleString()
                        : "Earlier"}
                    </span>
                    <button
                      aria-label="Delete report"
                      onClick={async () => {
                        await deleteReport(report.request_id);
                        refresh();
                      }}
                    >
                      ×
                    </button>
                  </div>
                );
              })}
            </div>
          </section>
        </>
      )}
    </main>
  );
}
