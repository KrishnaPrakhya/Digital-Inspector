"use client";

import { useEffect } from "react";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { console.error(error); }, [error]);
  return <main className="page-shell loading"><div className="empty-state panel"><div className="empty-icon">!</div><h1>Something interrupted this screen.</h1><p>Your locally saved reports are still on this device. Retry the screen or return to a fresh analysis.</p><div className="hero-actions"><button className="button primary" onClick={reset}>Try again</button><a className="button secondary" href="/analyze">Open analyzer</a></div></div></main>;
}
