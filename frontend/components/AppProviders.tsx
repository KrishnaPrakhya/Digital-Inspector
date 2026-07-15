"use client";

import { createContext, useContext, useMemo, useState } from "react";

type Locale = "en" | "hi";
const strings = {
  en: { analyze: "Analyze", library: "Scam library", landscape: "Threat map", dashboard: "My reports", portal: "Cybercrime portal", emergency: "Fraud in progress? Call 1930 now", language: "हिंदी" },
  hi: { analyze: "जाँच करें", library: "स्कैम लाइब्रेरी", landscape: "खतरे का नक्शा", dashboard: "मेरी रिपोर्ट", portal: "साइबरक्राइम पोर्टल", emergency: "धोखाधड़ी जारी है? अभी 1930 पर कॉल करें", language: "English" },
};

const LocaleContext = createContext({ locale: "en" as Locale, toggle: () => {}, t: strings.en });

export function AppProviders({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = useState<Locale>("en");
  const value = useMemo(() => ({ locale, toggle: () => setLocale((current) => current === "en" ? "hi" : "en"), t: strings[locale] }), [locale]);
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  return useContext(LocaleContext);
}
