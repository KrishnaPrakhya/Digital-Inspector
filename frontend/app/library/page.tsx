"use client";

import { useMemo, useState } from "react";

import { searchSimilarScripts, type SimilarScript } from "@/lib/api";
import { FAMILY_META, PLAYBOOKS, STAGE_META } from "@/lib/scam-content";

export default function LibraryPage() {
  const [filter, setFilter] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SimilarScript[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");

  const visible = useMemo(() => PLAYBOOKS.filter((item) => {
    const content = `${FAMILY_META[item.family].name} ${item.signs.join(" ")} ${item.example}`.toLowerCase();
    return content.includes(filter.toLowerCase());
  }), [filter]);

  async function searchCorpus() {
    if (query.trim().length < 3) return;
    setSearching(true); setError("");
    try { setResults(await searchSimilarScripts(query.trim(), 6)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "Search unavailable"); }
    finally { setSearching(false); }
  }

  return <main className="page-shell library-page">
    <div className="page-intro"><div><div className="eyebrow"><span /> Scam intelligence library</div><h1 className="page-title">Learn the script.<br />Break the spell.</h1></div><p>Explore common Indian scam playbooks, see how pressure escalates, and search 32,544 known scripts using the same multilingual E5 model used in analysis reports.</p></div>

    <section className="library-search panel"><div><label htmlFor="library-filter">Filter red flags</label><input id="library-filter" value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Try OTP, parcel, AnyDesk…" /></div><div><label htmlFor="corpus-search">Semantic script search</label><div className="search-row"><input id="corpus-search" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === "Enter" && searchCorpus()} placeholder="Describe what the caller said…" /><button className="button primary" onClick={searchCorpus} disabled={searching}>{searching ? "Searching…" : "Search AI corpus"}</button></div></div></section>
    {error && <div className="error" role="alert">{error}</div>}
    {results.length > 0 && <section className="search-results"><div className="section-kicker">Closest known scripts</div><div className="result-grid">{results.map((result) => <article className="script-result" key={result.script_id}><div><span style={{ color: FAMILY_META[result.family].color }}>{FAMILY_META[result.family].name}</span><b>{Math.round(result.similarity * 100)}% match</b></div><p>{result.excerpt}</p><small>{result.script_id}</small></article>)}</div></section>}

    <section className="playbook-grid">{visible.map((playbook, cardIndex) => { const meta = FAMILY_META[playbook.family]; return <article className="playbook-card" id={playbook.family} key={playbook.family} style={{ "--accent": meta.color } as React.CSSProperties}><div className="playbook-number">0{cardIndex + 1}</div><div className="family-icon large">{meta.name.slice(0, 2).toUpperCase()}</div><h2>{meta.name}</h2><p className="muted">{meta.short}</p><h3>Red flags</h3><ul>{playbook.signs.map((sign) => <li key={sign}><i />{sign}</li>)}</ul><div className="example-quote"><span>Example script</span>“{playbook.example}”</div><a className="button secondary" href="/analyze">Test this pattern →</a></article>; })}</section>

    <section className="section stage-guide"><div className="section-heading split-heading"><div><span>Pressure ladder</span><h2>Scams escalate in recognizable stages.</h2></div><p>A single sentence can be ambiguous. The sequence reveals intent: authority becomes urgency, urgency becomes isolation, and isolation creates the opening for credentials or payment.</p></div><div className="stage-ladder">{Object.entries(STAGE_META).filter(([id]) => id !== "s0_none").map(([id, stage]) => <article key={id}><b>{stage.order}</b><div><h3>{stage.name}</h3><p>{stage.description}</p></div></article>)}</div></section>
  </main>;
}
