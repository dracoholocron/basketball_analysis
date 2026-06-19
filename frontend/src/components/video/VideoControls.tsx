"use client";

import { useEffect, useState, type RefObject } from "react";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { clsx } from "clsx";

/**
 * Reusable transport controls for a <video>: play/pause, step one frame back/forward,
 * and playback speed (slow/fast). Drives the provided videoRef directly so it works
 * over any existing video element (annotation, highlights, lab, etc.).
 */
export default function VideoControls({
  videoRef,
  fps = 30,
  className,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  fps?: number;
  className?: string;
}) {
  const [playing, setPlaying] = useState(false);
  const [rate, setRate] = useState(1);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onPause);
    return () => {
      v.removeEventListener("play", onPlay);
      v.removeEventListener("pause", onPause);
    };
  }, [videoRef]);

  const step = (frames: number) => {
    const v = videoRef.current;
    if (!v) return;
    v.pause();
    const dt = frames / (fps || 30);
    v.currentTime = Math.max(0, Math.min(v.duration || Infinity, v.currentTime + dt));
  };
  const toggle = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) v.play(); else v.pause();
  };
  const setSpeed = (r: number) => {
    const v = videoRef.current;
    if (!v) return;
    v.playbackRate = r;
    setRate(r);
  };

  const btn = "p-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-white";
  return (
    <div className={clsx("flex items-center gap-2 flex-wrap", className)}>
      <button onClick={() => step(-1)} className={btn} title="Cuadro anterior">
        <SkipBack size={15} />
      </button>
      <button onClick={toggle} className={btn} title={playing ? "Pausar" : "Reproducir"}>
        {playing ? <Pause size={15} /> : <Play size={15} />}
      </button>
      <button onClick={() => step(1)} className={btn} title="Cuadro siguiente">
        <SkipForward size={15} />
      </button>
      <span className="text-xs text-slate-400 ml-2">Velocidad:</span>
      <div className="flex items-center gap-1 bg-slate-800 rounded-lg p-1">
        {[0.25, 0.5, 1, 2].map((r) => (
          <button
            key={r}
            onClick={() => setSpeed(r)}
            className={clsx(
              "px-2 py-1 text-xs rounded-md transition-colors",
              rate === r ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white",
            )}
          >
            {r}×
          </button>
        ))}
      </div>
    </div>
  );
}
