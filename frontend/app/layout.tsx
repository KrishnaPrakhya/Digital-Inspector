import type { Metadata } from "next";
import { SiteHeader } from "@/components/SiteHeader";
import "./globals.css";

export const metadata: Metadata = {
  title: "Digital Inspector — Scam Call Interceptor",
  description: "Detect Indian phone-scam patterns and prepare a cybercrime complaint.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body><SiteHeader />{children}</body>
    </html>
  );
}
