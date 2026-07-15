import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Digital Inspector — Scam Call Interceptor",
    short_name: "Digital Inspector",
    description: "Analyze suspicious calls and messages and act quickly.",
    start_url: "/",
    display: "standalone",
    background_color: "#090a0d",
    theme_color: "#090a0d",
    icons: [{ src: "/favicon.ico", sizes: "any", type: "image/x-icon" }],
  };
}
