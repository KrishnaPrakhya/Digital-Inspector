"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { getHealth, type HealthResponse } from "@/lib/api";

export function SiteHeader() {
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let active = true;
    const check = () => getHealth().then((value) => active && setHealth(value)).catch(() => active && setHealth(null));
    check();
    const timer = window.setInterval(check, 60_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <header className="site-header">
      <Link className="brand" href="/">
        <span className="brand-mark">DI</span>
        <span>Digital Inspector</span>
      </Link>
      <nav>
        <Link href="/analyze">Analyze</Link>
        <a href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">Cybercrime portal</a>
        <span className="health-pill" title={health ? "Backend reachable" : "Backend unavailable"}>
          <i className={health ? "online" : "offline"} />
          {health ? (health.asr.groq_configured ? "AI ready" : "Model ready") : "Checking API"}
        </span>
      </nav>
    </header>
  );
}

