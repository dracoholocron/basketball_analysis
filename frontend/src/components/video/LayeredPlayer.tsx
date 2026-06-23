"use client";

import { useEffect, useRef, useState } from "react";
import { getJobLayers } from "@/lib/api";
import { clsx } from "clsx";

// COCO-17 skeleton edges (must match the engine's pose_drawer).
const COCO_EDGES: [number, number][] = [
  [0, 1], [0, 2], [1, 3], [2, 4],
  [5, 6], [5, 7], [7, 9], [6, 8], [8, 10],
  [5, 11], [6, 12], [11, 12],
  [11, 13], [13, 15], [12, 14], [14, 16],
];

type Kpt = [number, number, number];
interface Layers {
  fps: number; width: number; height: number;
  poses: Record<string, Kpt[][]>;   // frame -> [perPlayer [ [x,y,c]*17 ]]
  ball: Record<string, number[]>;    // frame -> [x1,y1,x2,y2]
}

/** Post-hoc layer player: plays the RAW video and draws toggleable pose/ball overlays on a
 *  canvas synced to the current frame (no baked overlays). Falls back gracefully. */
export default function LayeredPlayer({ jobId }: { jobId: string }) {
  const [data, setData] = useState<{ raw: string; layers: Layers } | null>(null);
  const [showPoses, setShowPoses] = useState(true);
  const [showBall, setShowBall] = useState(true);
  const [loading, setLoading] = useState(true);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const urls = await getJobLayers(jobId);
      if (!urls || cancelled) { setLoading(false); return; }
      try {
        const layers = await fetch(urls.layers_url).then(r => r.json());
        if (!cancelled) setData({ raw: urls.raw_video_url, layers });
      } catch { /* ignore */ }
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [jobId]);

  useEffect(() => {
    const v = videoRef.current, c = canvasRef.current;
    if (!v || !c || !data) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const { layers } = data;

    const draw = () => {
      const dw = v.clientWidth, dh = v.clientHeight;
      if (c.width !== dw || c.height !== dh) { c.width = dw; c.height = dh; }
      ctx.clearRect(0, 0, dw, dh);
      const sx = dw / (layers.width || dw), sy = dh / (layers.height || dh);
      const f = Math.round(v.currentTime * (layers.fps || 25));

      if (showPoses) {
        const players = layers.poses?.[String(f)];
        if (players) {
          ctx.lineWidth = 2; ctx.strokeStyle = "rgba(0,255,255,0.9)"; ctx.fillStyle = "rgba(255,255,0,0.9)";
          for (const kp of players) {
            if (!kp || kp.length < 17) continue;
            for (const [a, b] of COCO_EDGES) {
              if (kp[a][2] > 0.3 && kp[b][2] > 0.3) {
                ctx.beginPath(); ctx.moveTo(kp[a][0] * sx, kp[a][1] * sy);
                ctx.lineTo(kp[b][0] * sx, kp[b][1] * sy); ctx.stroke();
              }
            }
            for (const p of kp) {
              if (p[2] > 0.3) { ctx.beginPath(); ctx.arc(p[0] * sx, p[1] * sy, 3, 0, 6.28); ctx.fill(); }
            }
          }
        }
      }
      if (showBall) {
        const b = layers.ball?.[String(f)];
        if (b && b.length >= 4) {
          ctx.strokeStyle = "rgba(34,197,94,0.95)"; ctx.lineWidth = 2;
          ctx.strokeRect(b[0] * sx, b[1] * sy, (b[2] - b[0]) * sx, (b[3] - b[1]) * sy);
        }
      }
      rafRef.current = requestAnimationFrame(draw);
    };
    rafRef.current = requestAnimationFrame(draw);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [data, showPoses, showBall]);

  if (loading) return null;
  if (!data) return null;

  return (
    <div className="space-y-2">
      <div className="relative inline-block w-full">
        <video ref={videoRef} src={data.raw} controls className="w-full rounded-lg bg-black" />
        <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none" />
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span className="text-slate-400">Capas:</span>
        {([["Poses", showPoses, setShowPoses], ["Balón", showBall, setShowBall]] as const).map(([label, on, set]) => (
          <button key={label} onClick={() => set(v => !v)}
            className={clsx("px-3 py-1 rounded-md transition-colors",
              on ? "bg-blue-600 text-white" : "bg-slate-700 text-slate-400")}>
            {label} {on ? "✓" : ""}
          </button>
        ))}
        <span className="text-slate-500 ml-2">Sobre el video original (sin overlays horneados)</span>
      </div>
    </div>
  );
}
