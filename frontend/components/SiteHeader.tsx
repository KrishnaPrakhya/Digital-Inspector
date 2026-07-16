"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useLocale } from "@/components/AppProviders";
import { getHealth, type HealthResponse } from "@/lib/api";

export function SiteHeader() {
  const pathname = usePathname();
  const { t, toggle } = useLocale();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    let active = true;
    const check = () =>
      getHealth()
        .then((value) => active && setHealth(value))
        .catch(() => active && setHealth(null));
    check();
    const timer = window.setInterval(check, 60_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const nav = [
    ["/analyze", t.analyze],
    ["/library", t.library],
    ["/landscape", t.landscape],
    ["/dashboard", t.dashboard],
  ];
  const readyCount = health
    ? Object.values(health.models).filter(Boolean).length
    : 0;

  return (
    <>
      <a className="emergency-strip" href="tel:1930">
        <span>●</span>
        {t.emergency}
        <b>1930 →</b>
      </a>
      <header className="site-header">
        <Link className="brand" href="/" onClick={() => setMenuOpen(false)}>
          <span className="brand-mark">DI</span>
          <span>
            <b>Digital</b> Inspector
          </span>
        </Link>
        <button
          className="menu-button"
          aria-label="Toggle navigation"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((value) => !value)}
        >
          <span />
          <span />
        </button>
        <nav className={menuOpen ? "open" : ""} aria-label="Primary navigation">
          {nav.map(([href, label]) => (
            <Link
              className={pathname.startsWith(href) ? "active" : ""}
              href={href}
              key={href}
              onClick={() => setMenuOpen(false)}
            >
              {label}
            </Link>
          ))}
          <a href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">
            {t.portal} ↗
          </a>
          <button className="language-button" onClick={toggle}>
            {t.language}
          </button>
        </nav>
      </header>
    </>
  );
}
