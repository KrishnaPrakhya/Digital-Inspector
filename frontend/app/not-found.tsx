import Link from "next/link";

export default function NotFound() {
  return <main className="page-shell loading"><div className="empty-state panel"><div className="empty-icon">404</div><h1>This page is not in the playbook.</h1><p>The link may be outdated, or the report belongs to another browser.</p><div className="hero-actions"><Link className="button primary" href="/analyze">Analyze evidence</Link><Link className="button secondary" href="/">Go home</Link></div></div></main>;
}
