"use client";

import { useEffect, useRef } from "react";
import WaveSurfer from "wavesurfer.js";

export function Waveform({ url }: { url: string }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!host.current) return;
    const wave = WaveSurfer.create({
      container: host.current,
      url,
      height: 76,
      waveColor: "#6b7280",
      progressColor: "#ef4444",
      cursorColor: "#fbbf24",
      barWidth: 2,
      barGap: 2,
      barRadius: 2,
    });
    wave.on("interaction", () => wave.playPause());
    return () => wave.destroy();
  }, [url]);

  return <div className="waveform" ref={host} aria-label="Audio waveform; click to play or pause" />;
}

