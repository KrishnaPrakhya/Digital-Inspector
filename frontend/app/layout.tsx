import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { AppProviders } from "@/components/AppProviders";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Digital Inspector — Scam Call Interceptor",
  description:
    "Detect Indian phone-scam patterns and prepare a cybercrime complaint.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html className={inter.variable} lang="en">
      <body>
        <AppProviders>
          <SiteHeader />
          <div className="app-content">{children}</div>
          <SiteFooter />
        </AppProviders>
      </body>
    </html>
  );
}
