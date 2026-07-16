"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  ALL_INDIA_CASES_2023,
  LandscapeMetric,
  percentChange,
  STATE_CYBER_SIGNALS,
  type StateCyberSignal,
} from "@/lib/cyber-landscape-data";

type Point = [number, number];
type TopologyGeometry = {
  type: "Polygon" | "MultiPolygon";
  arcs: number[][] | number[][][];
  properties: { st_nm: string };
};
type IndiaTopology = {
  transform: { scale: Point; translate: Point };
  arcs: Point[][];
  objects: { states: { geometries: TopologyGeometry[] } };
};

const WIDTH = 620;
const HEIGHT = 660;
const SOURCE_CASES =
  "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2238498&lang=2&reg=48";
const SOURCE_ORIGINS =
  "https://www.mha.gov.in/MHA1/Par2017/pdfs/par2024-pdfs/RS31072024/1029.pdf";
const NUMBER = new Intl.NumberFormat("en-IN");

function project([longitude, latitude]: Point): Point {
  const x = ((longitude - 67.4) / (98.8 - 67.4)) * WIDTH;
  const lat = (Math.max(-85, Math.min(85, latitude)) * Math.PI) / 180;
  const north = Math.log(Math.tan(Math.PI / 4 + (38.2 * Math.PI) / 360));
  const south = Math.log(Math.tan(Math.PI / 4 + (5.4 * Math.PI) / 360));
  const mercator = Math.log(Math.tan(Math.PI / 4 + lat / 2));
  return [x, ((north - mercator) / (north - south)) * HEIGHT];
}

function geometryPaths(topology: IndiaTopology) {
  const decoded = topology.arcs.map((arc) => {
    let x = 0;
    let y = 0;
    return arc.map(([dx, dy]) => {
      x += dx;
      y += dy;
      return [
        x * topology.transform.scale[0] + topology.transform.translate[0],
        y * topology.transform.scale[1] + topology.transform.translate[1],
      ] as Point;
    });
  });
  const getArc = (index: number) =>
    index < 0 ? [...decoded[~index]].reverse() : decoded[index];
  const ringPath = (indexes: number[]) => {
    const points = indexes.flatMap((index, position) => {
      const arc = getArc(index);
      return position ? arc.slice(1) : arc;
    });
    return (
      points
        .map((point, index) => {
          const [x, y] = project(point);
          return `${index ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join("") + "Z"
    );
  };
  return topology.objects.states.geometries.map((geometry) => {
    const polygons =
      geometry.type === "Polygon"
        ? [geometry.arcs as number[][]]
        : (geometry.arcs as number[][][]);
    return {
      name: geometry.properties.st_nm,
      path: polygons.flatMap((polygon) => polygon.map(ringPath)).join(""),
    };
  });
}

function caseFill(value: number) {
  if (value >= 15_000) return "#f04455";
  if (value >= 7_500) return "#c83343";
  if (value >= 3_000) return "#8f2836";
  if (value >= 1_000) return "#5d202a";
  if (value >= 250) return "#381820";
  return "#211318";
}

function changeFill(change: number | null) {
  if (change === null) return "#453b25";
  if (change >= 200) return "#f04455";
  if (change >= 75) return "#b93040";
  if (change >= 20) return "#782733";
  if (change >= 0) return "#432027";
  if (change <= -50) return "#164738";
  return "#245445";
}

function stateFill(signal: StateCyberSignal, metric: LandscapeMetric) {
  if (metric === "cases") return caseFill(signal.cases2023);
  if (metric === "change") return changeFill(percentChange(signal));
  return signal.originHubs?.length ? "#f5b942" : "#211318";
}

export default function CyberLandscapePage() {
  const [topology, setTopology] = useState<IndiaTopology | null>(null);
  const [selected, setSelected] = useState("Karnataka");
  const [metric, setMetric] = useState<LandscapeMetric>("cases");
  const [mapError, setMapError] = useState(false);

  useEffect(() => {
    fetch("/india-states.topojson")
      .then((response) => {
        if (!response.ok) throw new Error("Map unavailable");
        return response.json();
      })
      .then(setTopology)
      .catch(() => setMapError(true));
  }, []);

  const paths = useMemo(
    () => (topology ? geometryPaths(topology) : []),
    [topology],
  );
  const rankings = useMemo(
    () =>
      Object.entries(STATE_CYBER_SIGNALS).sort(
        (a, b) => b[1].cases2023 - a[1].cases2023,
      ),
    [],
  );
  const selectedSignal = STATE_CYBER_SIGNALS[selected];
  const selectedChange = percentChange(selectedSignal);
  const selectedRank = rankings.findIndex(([name]) => name === selected) + 1;
  const selectedShare = (selectedSignal.cases2023 / ALL_INDIA_CASES_2023) * 100;
  const maxTrend = Math.max(
    selectedSignal.cases2021,
    selectedSignal.cases2022,
    selectedSignal.cases2023,
  );

  return (
    <main className="page-shell landscape-page">
      <div className="page-intro landscape-intro">
        <div>
          <div className="eyebrow">
            <span /> India cybercrime landscape
          </div>
          <h1 className="page-title">
            See the signal.
            <br />
            Understand the limits.
          </h1>
        </div>
        <p>
          Explore where cybercrime cases were recorded and where suspect-number
          origin clusters were reported. Use this as a preparedness signal—not a
          prediction of who will be attacked.
        </p>
      </div>

      <section className="landscape-method">
        <div>
          <b>Latest comparable NCRB series</b>
          <span>2021–2023 police-registered cybercrime cases</span>
        </div>
        <div>
          <b>86,420</b>
          <span>cases registered across India in 2023</span>
        </div>
        <div>
          <b>20 named places</b>
          <span>suspect-number origin hubs reported by MHA in 2024</span>
        </div>
      </section>

      <section className="landscape-workbench">
        <div className="map-column">
          <div className="map-toolbar">
            <div>
              <span>Map layer</span>
              <div
                className="metric-switch"
                role="group"
                aria-label="Choose map metric"
              >
                <button
                  className={metric === "cases" ? "active" : ""}
                  onClick={() => setMetric("cases")}
                >
                  2023 cases
                </button>
                <button
                  className={metric === "change" ? "active" : ""}
                  onClick={() => setMetric("change")}
                >
                  Change since 2021
                </button>
                <button
                  className={metric === "origins" ? "active" : ""}
                  onClick={() => setMetric("origins")}
                >
                  Reported origin hubs
                </button>
              </div>
            </div>
            <small>Choose a state for context</small>
          </div>
          <div className="india-map-wrap">
            {mapError ? (
              <div className="map-loading">
                The boundary map could not load. State rankings remain
                available.
              </div>
            ) : !topology ? (
              <div className="map-loading">Loading India boundaries…</div>
            ) : (
              <svg
                className="india-map"
                viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
                role="img"
                aria-label={`India map showing ${metric === "cases" ? "2023 cybercrime cases" : metric === "change" ? "change in cases since 2021" : "reported suspect-number origin hubs"} by state`}
              >
                <title>India cybercrime reporting landscape</title>
                <desc>
                  Select a state to inspect registered cases, trend, national
                  share, and reported origination hubs.
                </desc>
                {paths.map(({ name, path }) => {
                  const signal = STATE_CYBER_SIGNALS[name];
                  if (!signal) return null;
                  const label = `${name}: ${NUMBER.format(signal.cases2023)} cases registered in 2023`;
                  return (
                    <path
                      d={path}
                      key={name}
                      fill={stateFill(signal, metric)}
                      className={selected === name ? "selected" : ""}
                      aria-label={label}
                      role="button"
                      tabIndex={0}
                      onClick={() => setSelected(name)}
                      onKeyDown={(event) =>
                        (event.key === "Enter" || event.key === " ") &&
                        setSelected(name)
                      }
                    >
                      <title>{label}</title>
                    </path>
                  );
                })}
              </svg>
            )}
            <div className={`map-legend ${metric}`} aria-label="Map legend">
              {metric === "cases" ? (
                <>
                  <span>
                    <i style={{ background: "#211318" }} />
                    Under 250
                  </span>
                  <span>
                    <i style={{ background: "#5d202a" }} />
                    1,000+
                  </span>
                  <span>
                    <i style={{ background: "#8f2836" }} />
                    3,000+
                  </span>
                  <span>
                    <i style={{ background: "#c83343" }} />
                    7,500+
                  </span>
                  <span>
                    <i style={{ background: "#f04455" }} />
                    15,000+
                  </span>
                </>
              ) : metric === "change" ? (
                <>
                  <span>
                    <i style={{ background: "#164738" }} />
                    Down 50%+
                  </span>
                  <span>
                    <i style={{ background: "#432027" }} />
                    Stable / rising
                  </span>
                  <span>
                    <i style={{ background: "#b93040" }} />
                    Up 75%+
                  </span>
                  <span>
                    <i style={{ background: "#f04455" }} />
                    Up 200%+
                  </span>
                </>
              ) : (
                <>
                  <span>
                    <i style={{ background: "#211318" }} />
                    No place named
                  </span>
                  <span>
                    <i style={{ background: "#f5b942" }} />
                    One or more places named
                  </span>
                </>
              )}
            </div>
          </div>
          <p className="map-caveat">
            <b>Read carefully:</b> higher recorded counts may reflect
            population, internet use, reporting access, police registration, or
            enforcement—not simply a higher personal chance of victimization.
            NCRB explicitly cautions against pure state-to-state comparison.
          </p>
        </div>

        <aside className="state-dossier" aria-live="polite">
          <div className="dossier-head">
            <span>Selected state / UT</span>
            <h2>{selected}</h2>
            <p>Rank #{selectedRank} by registered case volume in 2023</p>
          </div>
          <div className="dossier-numbers">
            <div>
              <strong>{NUMBER.format(selectedSignal.cases2023)}</strong>
              <span>registered cases · 2023</span>
            </div>
            <div>
              <strong>
                {selectedChange === null
                  ? "New"
                  : `${selectedChange >= 0 ? "+" : ""}${Math.round(selectedChange)}%`}
              </strong>
              <span>change from 2021</span>
            </div>
            <div>
              <strong>{selectedShare.toFixed(1)}%</strong>
              <span>share of India total</span>
            </div>
          </div>
          <div className="mini-trend">
            <div>
              <b>Three-year direction</b>
              <span>
                {selectedChange !== null && selectedChange > 25
                  ? "Recorded cases increased materially"
                  : selectedChange !== null && selectedChange < -25
                    ? "Recorded cases declined"
                    : "No sharp two-year shift"}
              </span>
            </div>
            {[
              ["2021", selectedSignal.cases2021],
              ["2022", selectedSignal.cases2022],
              ["2023", selectedSignal.cases2023],
            ].map(([year, value]) => (
              <div className="trend-row" key={year}>
                <span>{year}</span>
                <i>
                  <b
                    style={{
                      width: `${Math.max(2, (Number(value) / maxTrend) * 100)}%`,
                    }}
                  />
                </i>
                <strong>{NUMBER.format(Number(value))}</strong>
              </div>
            ))}
          </div>
          <div className="origin-detail">
            <span>MHA suspect-number origin signal</span>
            {selectedSignal.originHubs?.length ? (
              <>
                <h3>
                  {selectedSignal.originHubs.length} named{" "}
                  {selectedSignal.originHubs.length === 1 ? "place" : "places"}
                </h3>
                <div>
                  {selectedSignal.originHubs.map((hub) => (
                    <b key={hub}>{hub}</b>
                  ))}
                </div>
                <p>
                  These are places of origination linked to citizen-reported
                  suspect mobile numbers—not places where every caller or
                  resident is suspicious.
                </p>
              </>
            ) : (
              <>
                <h3>No place named in this 2024 list</h3>
                <p>
                  This does not mean the state is scam-free. Cybercrime is
                  borderless and the list covers only major reported origination
                  places for the cited period.
                </p>
              </>
            )}
          </div>
          <div className="dossier-action">
            <b>Location never changes the response.</b>
            <p>
              Stop the transfer, preserve the call or message, contact the bank
              through an official number, and report quickly.
            </p>
            <div>
              <a className="button primary" href="tel:1930">
                Call 1930
              </a>
              <Link className="button secondary" href="/analyze">
                Analyze evidence
              </Link>
            </div>
          </div>
        </aside>
      </section>

      <section className="ranking-section">
        <div className="section-heading split-heading">
          <div>
            <span>Recorded volume · 2023</span>
            <h2>Where reporting systems saw the most cases.</h2>
          </div>
          <p>
            The ranking gives operational context, not a “most dangerous state”
            label. Select any row to inspect its trend and MHA origin signal.
          </p>
        </div>
        <div className="state-ranking">
          {rankings.slice(0, 10).map(([name, signal], index) => (
            <button
              onClick={() => {
                setSelected(name);
                window.scrollTo({ top: 250, behavior: "smooth" });
              }}
              className={selected === name ? "active" : ""}
              key={name}
            >
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div>
                <b>{name}</b>
                <i>
                  <em
                    style={{
                      width: `${(signal.cases2023 / rankings[0][1].cases2023) * 100}%`,
                    }}
                  />
                </i>
              </div>
              <strong>{NUMBER.format(signal.cases2023)}</strong>
            </button>
          ))}
        </div>
      </section>

      <section className="source-panel">
        <div>
          <span>Method & provenance</span>
          <h2>Evidence before heat.</h2>
        </div>
        <p>
          Case counts are NCRB “Crime in India 2023” figures reproduced by the
          Ministry of Home Affairs. Origin hubs come from MHA’s 31 July 2024
          parliamentary answer and reflect suspect mobile numbers reported from
          1 January–22 July 2024. Boundaries are a published TopoJSON reference
          and are for visualization only.
        </p>
        <div>
          <a href={SOURCE_CASES} target="_blank" rel="noreferrer">
            NCRB/MHA cases source ↗
          </a>
          <a href={SOURCE_ORIGINS} target="_blank" rel="noreferrer">
            MHA origin-hub source ↗
          </a>
          <a
            href="https://github.com/udit-001/india-maps-data"
            target="_blank"
            rel="noreferrer"
          >
            Boundary reference ↗
          </a>
        </div>
      </section>
    </main>
  );
}
