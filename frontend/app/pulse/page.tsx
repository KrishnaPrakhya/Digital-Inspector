"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getThreatPulse, type PulseResponse, type PlaybookStage, type ScamFamily } from "@/lib/api";
import { FAMILY_META, STAGE_META } from "@/lib/scam-content";

const WINDOWS = [
  { days: 1, label: "24 hours" },
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
];

const LANGUAGE_LABELS: Record<string, string> = {
  en: "English",
  hi: "Hindi (Devanagari)",
  hinglish: "Hinglish (romanized)",
};

const EVIDENCE_LABELS: Record<string, string> = {
  upi_ids: "UPI handle demanded",
  amounts: "Specific amount named",
  phone_numbers: "Callback number given",
  agencies: "Authority impersonated",
  banks_apps: "Bank or app referenced",
  links: "Link sent",
};

const TOOLTIP_STYLE = {
  background: "#15171c",
  border: "1px solid #292c34",
  borderRadius: 10,
};

const reveal = {
  hidden: { opacity: 0, y: 14 },
  show: (index: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: 0.06 * index, duration: 0.42, ease: [0.22, 1, 0.36, 1] as const },
  }),
};

export default function PulsePage() {
  const [data, setData] = useState<PulseResponse | null>(null);
  const [days, setDays] = useState(7);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (window: number) => {
    setLoading(true);
    setError("");
    try {
      setData(await getThreatPulse(window));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not reach the threat feed.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(days);
  }, [days, load]);

  const totals = data?.totals;
  const families = (data?.families ?? []).map((row) => ({
    ...row,
    name: FAMILY_META[row.family as ScamFamily]?.name ?? row.family,
    color: FAMILY_META[row.family as ScamFamily]?.color ?? "#64748b",
  }));
  const stages = (data?.stages ?? [])
    .map((row) => ({
      ...row,
      name: STAGE_META[row.stage as PlaybookStage]?.name ?? row.stage,
      order: STAGE_META[row.stage as PlaybookStage]?.order ?? 9,
    }))
    .sort((a, b) => a.order - b.order);
  const daily = (data?.daily ?? []).map((row) => ({
    ...row,
    label: new Date(row.day).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
  }));
  const topFamily = families[0];
  const escalationRate =
    totals && totals.scams > 0
      ? Math.round(((stages.find((s) => s.stage === "s5_payment_demand")?.count ?? 0) / totals.scams) * 100)
      : 0;

  return (
    <main className="page-shell">
      <div className="page-intro">
        <div>
          <div className="eyebrow">
            <span /> Collective threat feed
          </div>
          <h1 className="page-title">
            The scam pulse.
            <br />
            Built from every analysis.
          </h1>
        </div>
        <p>
          Each analysis anonymously contributes the shape of the attack — never its content. No
          transcript, no phone number, no UPI handle, and no account is ever stored here. Your report
          stays in your browser.
        </p>
      </div>

      <div className="privacy-ribbon">
        <span>◉</span>
        <div>
          <b>Anonymous by construction</b>
          <small>
            Only the scam family, playbook stages reached, language, and which kinds of evidence
            appeared are recorded.
          </small>
        </div>
      </div>

      <div className="mode-tabs">
        {WINDOWS.map((window) => (
          <button
            className={days === window.days ? "active" : ""}
            key={window.days}
            onClick={() => setDays(window.days)}
            type="button"
          >
            <b>Last {window.label}</b>
            <small>Rolling window</small>
          </button>
        ))}
      </div>

      {error && <div className="notice">{error}</div>}

      {!error && data && !data.available && (
        <section className="panel report-section">
          <div className="empty-inline">
            The threat feed is not enabled on this deployment. Analyses still work normally — the
            feed is an optional aggregate layer.
          </div>
        </section>
      )}

      {!error && loading && !data && (
        <section className="panel report-section">
          <div className="empty-inline">Loading the threat feed…</div>
        </section>
      )}

      {!error && data?.available && totals && (
        <>
          {totals.analyses === 0 ? (
            <section className="panel report-section">
              <div className="empty-inline">
                No analyses recorded in this window yet. <Link href="/analyze">Analyze evidence</Link>{" "}
                and it will appear here within seconds.
              </div>
            </section>
          ) : (
            <>
              <motion.section animate="show" className="pulse-stats" custom={0} initial="hidden" key={days} variants={reveal}>
                <div className="panel">
                  <span>Analyses run</span>
                  <strong>{totals.analyses.toLocaleString()}</strong>
                  <small>Across every input type</small>
                </div>
                <div className="panel">
                  <span>Scam patterns found</span>
                  <strong>{totals.scams.toLocaleString()}</strong>
                  <small>{totals.analyses > 0 ? Math.round((totals.scams / totals.analyses) * 100) : 0}% of all analyses</small>
                </div>
                <div className="panel">
                  <span>High risk</span>
                  <strong>{totals.high_risk.toLocaleString()}</strong>
                  <small>Scored 55 or above</small>
                </div>
                <div className="panel">
                  <span>Escalated to payment</span>
                  <strong>{escalationRate}%</strong>
                  <small>Reached a payment demand</small>
                </div>
              </motion.section>

              <motion.div animate="show" className="report-layout" custom={1} initial="hidden" variants={reveal}>
                <div className="report-main">
                  <section className="panel report-section">
                    <div className="panel-title">
                      <div>
                        <span>Trend</span>
                        <h2>Scams detected per day</h2>
                      </div>
                      <small>{days}-day window</small>
                    </div>
                    <div className="chart-wrap">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={daily}>
                          <XAxis dataKey="label" stroke="#6b7280" fontSize={11} tickLine={false} />
                          <YAxis allowDecimals={false} stroke="#6b7280" fontSize={11} tickLine={false} width={28} />
                          <Tooltip contentStyle={TOOLTIP_STYLE} />
                          <Area
                            dataKey="scams"
                            fill="#fb7185"
                            fillOpacity={0.18}
                            stroke="#fb7185"
                            strokeWidth={2}
                            type="monotone"
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </section>

                  <section className="panel report-section">
                    <div className="panel-title">
                      <div>
                        <span>Playbook</span>
                        <h2>How far scammers push</h2>
                      </div>
                      <small>Stages reached</small>
                    </div>
                    <div className="chart-wrap">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={stages} layout="vertical" margin={{ left: 8 }}>
                          <XAxis type="number" allowDecimals={false} stroke="#6b7280" fontSize={11} tickLine={false} />
                          <YAxis
                            dataKey="name"
                            type="category"
                            stroke="#6b7280"
                            fontSize={10}
                            tickLine={false}
                            width={112}
                          />
                          <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "#ffffff08" }} />
                          <Bar dataKey="count" fill="#fb7185" radius={[0, 4, 4, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </section>
                </div>

                <aside className="report-aside">
                  <section className="panel report-section probability-panel">
                    <div className="panel-title">
                      <div>
                        <span>Distribution</span>
                        <h2>Scam families</h2>
                      </div>
                    </div>
                    <div className="chart-wrap">
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie
                            data={families}
                            dataKey="count"
                            nameKey="name"
                            innerRadius={58}
                            outerRadius={88}
                            paddingAngle={3}
                          >
                            {families.map((entry) => (
                              <Cell fill={entry.color} key={entry.family} />
                            ))}
                          </Pie>
                          <Tooltip contentStyle={TOOLTIP_STYLE} />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                    {topFamily && (
                      <p className="pulse-callout">
                        <b style={{ color: topFamily.color }}>{topFamily.name}</b> is the most
                        reported pattern right now.
                      </p>
                    )}
                    {families.map((row) => (
                      <div className="probability-row" key={row.family}>
                        <div>
                          <span>{row.name}</span>
                          <b>{row.count}</b>
                        </div>
                        <i>
                          <span
                            style={{
                              width: `${totals.scams > 0 ? (row.count / totals.scams) * 100 : 0}%`,
                              background: row.color,
                            }}
                          />
                        </i>
                      </div>
                    ))}
                  </section>

                  <section className="panel report-section">
                    <div className="panel-title">
                      <div>
                        <span>Reach</span>
                        <h2>Language of the attack</h2>
                      </div>
                    </div>
                    {(data.languages ?? []).map((row) => (
                      <div className="probability-row" key={row.language}>
                        <div>
                          <span>{LANGUAGE_LABELS[row.language] ?? row.language}</span>
                          <b>{row.count}</b>
                        </div>
                        <i>
                          <span
                            style={{
                              width: `${totals.analyses > 0 ? (row.count / totals.analyses) * 100 : 0}%`,
                              background: "#38bdf8",
                            }}
                          />
                        </i>
                      </div>
                    ))}
                  </section>

                  <section className="panel report-section">
                    <div className="panel-title">
                      <div>
                        <span>Evidence</span>
                        <h2>What scammers asked for</h2>
                      </div>
                    </div>
                    {(data.evidence ?? []).length ? (
                      (data.evidence ?? []).map((row) => (
                        <div className="probability-row" key={row.kind}>
                          <div>
                            <span>{EVIDENCE_LABELS[row.kind] ?? row.kind}</span>
                            <b>{totals.scams > 0 ? Math.round((row.count / totals.scams) * 100) : 0}%</b>
                          </div>
                          <i>
                            <span
                              style={{
                                width: `${totals.scams > 0 ? (row.count / totals.scams) * 100 : 0}%`,
                                background: "#f59e0b",
                              }}
                            />
                          </i>
                        </div>
                      ))
                    ) : (
                      <div className="empty-inline">No evidence patterns recorded yet.</div>
                    )}
                  </section>
                </aside>
              </motion.div>
            </>
          )}
        </>
      )}
    </main>
  );
}
