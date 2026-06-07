"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { clsx } from "clsx";
import { Loader2 } from "lucide-react";

interface PlayerTrack {
  track_id: number;
  bbox: [number, number, number, number]; // x1, y1, x2, y2 in pixels
  team: number;
}

interface KeypointEntry {
  frame: number;
  person_id: number;
  keypoints?: Record<string, [number, number]>;
  bbox?: [number, number, number, number];
  hoop_bbox?: [number, number, number, number];
  hoop_conf?: number;
}

interface FrameTrack {
  frame: number;
  players: PlayerTrack[];
}

// COCO skeleton connections
const SKELETON_PAIRS: [string, string][] = [
  ["left_shoulder", "right_shoulder"],
  ["left_shoulder", "left_elbow"],
  ["left_elbow", "left_wrist"],
  ["right_shoulder", "right_elbow"],
  ["right_elbow", "right_wrist"],
  ["left_shoulder", "left_hip"],
  ["right_shoulder", "right_hip"],
  ["left_hip", "right_hip"],
  ["left_hip", "left_knee"],
  ["left_knee", "left_ankle"],
  ["right_hip", "right_knee"],
  ["right_knee", "right_ankle"],
  ["nose", "left_eye"],
  ["nose", "right_eye"],
];

const TEAM_COLORS = ["#6b7280", "#2563eb", "#7c3aed"];

type OverlayMode = "bbox" | "skeleton" | "both";

interface Props {
  videoUrl: string;
  tracksUrl?: string;
  keypointsData?: KeypointEntry[];
  fps?: number;
  mode?: OverlayMode;
  className?: string;
}

export function VideoWithOverlay({
  videoUrl, tracksUrl, keypointsData, fps = 25, mode = "bbox", className,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const tracksMap = useRef<Map<number, PlayerTrack[]>>(new Map());
  const [loadingTracks, setLoadingTracks] = useState(false);
  const [tracksLoaded, setTracksLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rafCallbackRef = useRef<number | null>(null);

  // Load tracks JSONL line by line
  const loadTracks = useCallback(async (url: string) => {
    setLoadingTracks(true);
    setError(null);
    const map = new Map<number, PlayerTrack[]>();
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const reader = resp.body?.getReader();
      if (!reader) throw new Error("No stream");
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const obj = JSON.parse(line) as FrameTrack;
            map.set(obj.frame, obj.players);
          } catch { /* skip bad lines */ }
        }
      }
      tracksMap.current = map;
      setTracksLoaded(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load tracks");
    } finally {
      setLoadingTracks(false);
    }
  }, []);

  useEffect(() => {
    if (tracksUrl) loadTracks(tracksUrl);
  }, [tracksUrl, loadTracks]);

  const drawOverlay = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    canvas.width = video.videoWidth || video.clientWidth;
    canvas.height = video.videoHeight || video.clientHeight;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const currentFrame = Math.floor(video.currentTime * fps);

    // Draw bbox overlays
    if ((mode === "bbox" || mode === "both") && tracksMap.current.size > 0) {
      const players = tracksMap.current.get(currentFrame) ?? [];
      for (const p of players) {
        const [x1, y1, x2, y2] = p.bbox;
        const color = TEAM_COLORS[p.team] ?? TEAM_COLORS[0];
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
        ctx.fillStyle = color;
        ctx.fillRect(x1, y1 - 18, 32, 18);
        ctx.fillStyle = "white";
        ctx.font = "bold 11px sans-serif";
        ctx.fillText(`#${p.track_id}`, x1 + 3, y1 - 4);
      }
    }

    // Draw skeleton overlays from keypoints
    if ((mode === "skeleton" || mode === "both") && keypointsData) {
      const frameKps = keypointsData.filter((k) => k.frame === currentFrame);
      for (const entry of frameKps) {
        if (!entry.keypoints) continue;
        const kps = entry.keypoints;
        ctx.strokeStyle = "#22c55e";
        ctx.lineWidth = 2;
        for (const [a, b] of SKELETON_PAIRS) {
          const ptA = kps[a];
          const ptB = kps[b];
          if (!ptA || !ptB) continue;
          ctx.beginPath();
          ctx.moveTo(ptA[0], ptA[1]);
          ctx.lineTo(ptB[0], ptB[1]);
          ctx.stroke();
        }
        // Draw keypoint dots
        ctx.fillStyle = "#22c55e";
        for (const [, pt] of Object.entries(kps)) {
          ctx.beginPath();
          ctx.arc(pt[0], pt[1], 3, 0, Math.PI * 2);
          ctx.fill();
        }
        // Draw hoop bbox
        if (entry.hoop_bbox) {
          const [hx1, hy1, hx2, hy2] = entry.hoop_bbox;
          ctx.strokeStyle = "#84cc16";
          ctx.lineWidth = 2;
          ctx.setLineDash([4, 2]);
          ctx.strokeRect(hx1, hy1, hx2 - hx1, hy2 - hy1);
          ctx.setLineDash([]);
          if (entry.hoop_conf != null) {
            ctx.fillStyle = "#84cc16";
            ctx.font = "10px sans-serif";
            ctx.fillText(`Hoop ${(entry.hoop_conf * 100).toFixed(0)}%`, hx1, hy1 - 4);
          }
        }
      }
    }

    // Request next frame via rVFC if available
    if ("requestVideoFrameCallback" in video) {
      (video as HTMLVideoElement & { requestVideoFrameCallback: (cb: () => void) => number }).requestVideoFrameCallback(drawOverlay);
    }
  }, [fps, mode, keypointsData]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onPlay = () => {
      if ("requestVideoFrameCallback" in video) {
        (video as HTMLVideoElement & { requestVideoFrameCallback: (cb: () => void) => number }).requestVideoFrameCallback(drawOverlay);
      } else {
        const tick = () => { drawOverlay(); rafCallbackRef.current = requestAnimationFrame(tick); };
        rafCallbackRef.current = requestAnimationFrame(tick);
      }
    };
    const onPause = () => { if (rafCallbackRef.current) cancelAnimationFrame(rafCallbackRef.current); drawOverlay(); };
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);
    video.addEventListener("seeked", drawOverlay);
    return () => {
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
      video.removeEventListener("seeked", drawOverlay);
      if (rafCallbackRef.current) cancelAnimationFrame(rafCallbackRef.current);
    };
  }, [drawOverlay]);

  return (
    <div className={clsx("relative", className)}>
      <video ref={videoRef} src={videoUrl} controls className="w-full rounded-xl" />
      <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none rounded-xl" />
      {loadingTracks && (
        <div className="absolute top-2 right-2 flex items-center gap-1.5 bg-black/60 text-white text-xs px-2 py-1 rounded-full">
          <Loader2 size={11} className="animate-spin" /> Loading tracks…
        </div>
      )}
      {tracksLoaded && !loadingTracks && (
        <div className="absolute top-2 right-2 bg-green-600/80 text-white text-xs px-2 py-1 rounded-full">
          Overlay active
        </div>
      )}
      {error && (
        <div className="absolute top-2 right-2 bg-red-500/80 text-white text-xs px-2 py-1 rounded-full">
          Tracks error: {error}
        </div>
      )}
    </div>
  );
}
