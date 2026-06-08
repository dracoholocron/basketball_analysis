"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import {
  detectCameraMotion,
  getGameAnnotation,
  getLandmarkCatalog,
  getGameVideoUrl,
  putGameAnnotation,
  type LandmarkCatalogItem,
  type LandmarkPoint,
} from "@/lib/api";
import {
  AlertCircle,
  ArrowLeft,
  Camera,
  CheckCircle2,
  Info,
  Loader2,
  MapPin,
  Save,
  Trash2,
  Wind,
} from "lucide-react";
import { clsx } from "clsx";

// ── Category colors ──────────────────────────────────────────────────────────

const CAT_COLORS: Record<string, string> = {
  corner: "#f97316",   // orange
  circle: "#22d3ee",   // cyan
  line:   "#4ade80",   // green
  key:    "#facc15",   // yellow
  hoop:   "#f472b6",   // pink
};

const CAT_RING: Record<string, string> = {
  corner: "border-orange-500",
  circle: "border-cyan-400",
  line:   "border-green-400",
  key:    "border-yellow-400",
  hoop:   "border-pink-400",
};

function getCatColor(cat: string) {
  return CAT_COLORS[cat] ?? "#94a3b8";
}

// ── Motion banner config ──────────────────────────────────────────────────────

const MOTION_BANNER: Record<string, { bg: string; icon: React.ReactNode; msg: string }> = {
  static: {
    bg: "bg-green-900/40 border-green-700/50",
    icon: <CheckCircle2 size={16} className="text-green-400 shrink-0" />,
    msg: "Camera is stationary — annotate landmarks at any single frame.",
  },
  moderate: {
    bg: "bg-yellow-900/40 border-yellow-700/50",
    icon: <Info size={16} className="text-yellow-400 shrink-0" />,
    msg: "Some camera movement detected — consider marking the same landmarks at 2–3 different frames for better accuracy.",
  },
  moving: {
    bg: "bg-red-900/40 border-red-700/50",
    icon: <Wind size={16} className="text-red-400 shrink-0" />,
    msg: "Camera moves significantly — mark landmarks at multiple keyframes (every ~10 s) for accurate tracking.",
  },
  unknown: {
    bg: "bg-slate-700/40 border-slate-600/50",
    icon: <Info size={16} className="text-slate-400 shrink-0" />,
    msg: "Motion detection unavailable. Annotate landmarks at the frame that best shows the court.",
  },
};

// ── Main component ────────────────────────────────────────────────────────────

export default function AnnotatePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [catalog, setCatalog] = useState<LandmarkCatalogItem[]>([]);
  const [selectedLandmarkId, setSelectedLandmarkId] = useState<string>("");
  const [placed, setPlaced] = useState<LandmarkPoint[]>([]);
  const [motion, setMotion] = useState<string | null>(null);
  const [detectingMotion, setDetectingMotion] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [videoError, setVideoError] = useState(false);

  // Fetch catalog, existing annotation, and video URL on mount
  useEffect(() => {
    if (!id) return;

    getLandmarkCatalog()
      .then((c) => {
        setCatalog(c);
        if (c.length > 0) setSelectedLandmarkId(c[0].id);
      })
      .catch(() => null);

    getGameAnnotation(id)
      .then((ann) => {
        if (ann?.landmarks && ann.landmarks.length > 0) {
          setPlaced(ann.landmarks);
        }
        if (ann?.camera_motion) setMotion(ann.camera_motion);
      })
      .catch(() => null);

    getGameVideoUrl(id)
      .then((url) => setVideoUrl(url))
      .catch(() => setVideoError(true));
  }, [id]);

  // Run motion detection once video metadata is loaded
  const handleVideoLoaded = useCallback(async () => {
    if (!id || motion) return;
    setDetectingMotion(true);
    try {
      const res = await detectCameraMotion(id);
      setMotion(res.motion);
    } catch {
      setMotion("unknown");
    } finally {
      setDetectingMotion(false);
    }
  }, [id, motion]);

  // Draw markers on canvas whenever placed landmarks change
  useEffect(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!canvas || !video) return;

    canvas.width = video.clientWidth;
    canvas.height = video.clientHeight;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    placed.forEach((lm, idx) => {
      const cat = catalog.find((c) => c.id === lm.landmark_id);
      const color = getCatColor(cat?.category ?? "");
      const [x, y] = lm.pixel;

      ctx.beginPath();
      ctx.arc(x, y, 8, 0, Math.PI * 2);
      ctx.fillStyle = color + "cc";
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.fillStyle = "#fff";
      ctx.font = "bold 10px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(String(idx + 1), x, y + 4);
    });
  }, [placed, catalog]);

  // Handle canvas click → place landmark
  const handleCanvasClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!selectedLandmarkId) return;
      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const frame_t = videoRef.current?.currentTime ?? 0;

      setPlaced((prev) => {
        // If same landmark_id at the same frame_t already exists, update it
        const existingIdx = prev.findIndex(
          (p) => p.landmark_id === selectedLandmarkId && Math.abs(p.frame_t - frame_t) < 0.5
        );
        if (existingIdx >= 0) {
          const next = [...prev];
          next[existingIdx] = { landmark_id: selectedLandmarkId, pixel: [x, y], frame_t };
          return next;
        }
        return [...prev, { landmark_id: selectedLandmarkId, pixel: [x, y], frame_t }];
      });

      // Auto-advance to the next unplaced landmark
      const currentIdx = catalog.findIndex((c) => c.id === selectedLandmarkId);
      if (currentIdx >= 0 && currentIdx < catalog.length - 1) {
        setSelectedLandmarkId(catalog[currentIdx + 1].id);
      }
    },
    [selectedLandmarkId, catalog]
  );

  const removeLandmark = (idx: number) => {
    setPlaced((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSave = async () => {
    if (!id || placed.length < 4) return;
    setSaving(true);
    setSaveError(null);
    try {
      await putGameAnnotation(id, placed, motion ?? undefined);
      setSaved(true);
      setTimeout(() => router.push(`/games/${id}`), 1000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Save failed";
      setSaveError(msg);
    } finally {
      setSaving(false);
    }
  };

  const catGroups = catalog.reduce(
    (acc, c) => {
      if (!acc[c.category]) acc[c.category] = [];
      acc[c.category].push(c);
      return acc;
    },
    {} as Record<string, LandmarkCatalogItem[]>
  );

  return (
    <AppShell>
      <div className="max-w-7xl mx-auto space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link
              href={`/games/${id}`}
              className="p-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300"
            >
              <ArrowLeft size={16} />
            </Link>
            <div>
              <h1 className="text-xl font-bold text-white">Annotate Court</h1>
              <p className="text-sm text-slate-400">
                Click on the video to place court landmarks for homography calibration
              </p>
            </div>
          </div>

          <button
            onClick={handleSave}
            disabled={placed.length < 4 || saving || saved}
            className={clsx(
              "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
              placed.length >= 4 && !saved
                ? "bg-blue-600 hover:bg-blue-700 text-white"
                : saved
                ? "bg-green-600 text-white"
                : "bg-slate-700 text-slate-400 cursor-not-allowed"
            )}
          >
            {saving ? (
              <Loader2 size={14} className="animate-spin" />
            ) : saved ? (
              <CheckCircle2 size={14} />
            ) : (
              <Save size={14} />
            )}
            {saved ? "Saved!" : `Save (${placed.length}/4 min)`}
          </button>
        </div>

        {/* Motion detection banner */}
        {(motion || detectingMotion) && (
          <div
            className={clsx(
              "flex items-start gap-3 px-4 py-3 rounded-lg border text-sm",
              detectingMotion
                ? "bg-slate-700/40 border-slate-600/50 text-slate-400"
                : MOTION_BANNER[motion!]?.bg ?? "bg-slate-700/40 border-slate-600/50"
            )}
          >
            {detectingMotion ? (
              <Loader2 size={16} className="text-slate-400 shrink-0 animate-spin mt-0.5" />
            ) : (
              <span className="mt-0.5">{MOTION_BANNER[motion!]?.icon}</span>
            )}
            <span className="text-slate-200">
              {detectingMotion
                ? "Detecting camera motion…"
                : MOTION_BANNER[motion!]?.msg}
            </span>
          </div>
        )}

        {saveError && (
          <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-red-900/30 border border-red-700/50 text-sm text-red-300">
            <AlertCircle size={14} />
            {saveError}
          </div>
        )}

        {/* Main layout: video + sidebar */}
        <div className="flex gap-4">
          {/* Video + canvas */}
          <div className="flex-1 min-w-0">
            <div
              ref={containerRef}
              className="relative bg-black rounded-xl overflow-hidden"
              style={{ aspectRatio: "16/9" }}
            >
              {videoError ? (
                <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-2">
                  <Camera size={48} className="opacity-30" />
                  <p className="text-sm">No se pudo cargar el video</p>
                </div>
              ) : videoUrl ? (
                <>
                  <video
                    ref={videoRef}
                    src={videoUrl}
                    controls
                    className="w-full h-full object-contain"
                    onLoadedMetadata={handleVideoLoaded}
                  />
                  <canvas
                    ref={canvasRef}
                    onClick={handleCanvasClick}
                    className="absolute inset-0 w-full h-full cursor-crosshair"
                    style={{ pointerEvents: selectedLandmarkId ? "auto" : "none" }}
                  />
                </>
              ) : (
                <div className="flex items-center justify-center h-full text-slate-500 gap-2">
                  <Loader2 size={24} className="animate-spin opacity-50" />
                  <p className="text-sm">Cargando video…</p>
                </div>
              )}
            </div>

            {/* Tip */}
            <p className="mt-2 text-xs text-slate-500">
              Tip: pause the video at a frame where the court lines are clearly visible, then click
              to place each landmark. For moving cameras, use{" "}
              <strong className="text-slate-400">different timestamps</strong> for the same landmark
              to create keyframes.
            </p>
          </div>

          {/* Sidebar */}
          <div className="w-80 shrink-0 flex flex-col gap-4">
            {/* Landmark selector */}
            <div className="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <MapPin size={14} />
                Select landmark to place
              </h2>

              <select
                value={selectedLandmarkId}
                onChange={(e) => setSelectedLandmarkId(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {Object.entries(catGroups).map(([cat, items]) => (
                  <optgroup
                    key={cat}
                    label={cat.charAt(0).toUpperCase() + cat.slice(1)}
                  >
                    {items.map((lm) => (
                      <option key={lm.id} value={lm.id}>
                        {lm.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>

              {selectedLandmarkId && (
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <span
                    className="w-3 h-3 rounded-full shrink-0"
                    style={{
                      backgroundColor: getCatColor(
                        catalog.find((c) => c.id === selectedLandmarkId)?.category ?? ""
                      ),
                    }}
                  />
                  Click anywhere on the video to place
                </div>
              )}
            </div>

            {/* Placed landmarks list */}
            <div className="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3 flex-1 overflow-y-auto">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                Placed landmarks
                <span className="ml-auto text-xs font-normal text-slate-400">
                  {placed.length} / min 4
                </span>
              </h2>

              {placed.length === 0 ? (
                <p className="text-xs text-slate-500">
                  No landmarks placed yet. Select one above and click the video.
                </p>
              ) : (
                <ul className="space-y-2">
                  {placed.map((lm, idx) => {
                    const cat = catalog.find((c) => c.id === lm.landmark_id);
                    return (
                      <li
                        key={idx}
                        className={clsx(
                          "flex items-center gap-2 px-3 py-2 rounded-lg border text-xs",
                          "bg-slate-700/50 border-slate-600/50",
                          cat ? CAT_RING[cat.category] : "border-slate-600"
                        )}
                      >
                        <span
                          className="w-2.5 h-2.5 rounded-full shrink-0"
                          style={{ backgroundColor: getCatColor(cat?.category ?? "") }}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-white truncate">
                            {cat?.label ?? lm.landmark_id}
                          </div>
                          <div className="text-slate-400">
                            [{Math.round(lm.pixel[0])}, {Math.round(lm.pixel[1])}]
                            {lm.frame_t > 0 && (
                              <> · {lm.frame_t.toFixed(1)}s</>
                            )}
                          </div>
                        </div>
                        <button
                          onClick={() => removeLandmark(idx)}
                          className="p-1 rounded text-slate-500 hover:text-red-400 hover:bg-red-900/20"
                        >
                          <Trash2 size={12} />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            {/* Color legend */}
            <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
              <h2 className="text-xs font-semibold text-slate-400 mb-2">Legend</h2>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                {Object.entries(CAT_COLORS).map(([cat, color]) => (
                  <div key={cat} className="flex items-center gap-1.5 text-xs text-slate-400">
                    <span
                      className="w-2.5 h-2.5 rounded-full shrink-0"
                      style={{ backgroundColor: color }}
                    />
                    {cat}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
