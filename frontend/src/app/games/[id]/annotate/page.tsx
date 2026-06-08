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
  Pause,
  Play,
  Save,
  Trash2,
  Wind,
} from "lucide-react";
import { clsx } from "clsx";

// ── Category colors ──────────────────────────────────────────────────────────

const CAT_COLORS: Record<string, string> = {
  corner: "#f97316",
  circle: "#22d3ee",
  line:   "#4ade80",
  key:    "#facc15",
  hoop:   "#f472b6",
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

// ── Court diagram landmark positions (normalized 0-1 on full court) ──────────
// x: 0 = left baseline, 1 = right baseline
// y: 0 = top sideline, 1 = bottom sideline

const COURT_POSITIONS: Record<string, [number, number]> = {
  corner_tl:      [0.00, 0.00],
  corner_tr:      [1.00, 0.00],
  corner_br:      [1.00, 1.00],
  corner_bl:      [0.00, 1.00],
  center_circle:  [0.50, 0.50],
  midline_top:    [0.50, 0.00],
  midline_bottom: [0.50, 1.00],
  // Left key (x=0 is left baseline, key depth ~5.8m/28m ≈ 0.207, half-width ~2.45m/15m ≈ 0.163)
  key_tl_left:    [0.207, 0.337],
  key_bl_left:    [0.000, 0.337],
  key_tr_left:    [0.207, 0.663],
  key_br_left:    [0.000, 0.663],
  ftline_left:    [0.207, 0.500],
  hoop_left:      [0.056, 0.500],
  // Right key (mirror)
  key_tl_right:   [0.793, 0.337],
  key_bl_right:   [1.000, 0.337],
  key_tr_right:   [0.793, 0.663],
  key_br_right:   [1.000, 0.663],
  ftline_right:   [0.793, 0.500],
  hoop_right:     [0.944, 0.500],
};

// ── Motion banner config ─────────────────────────────────────────────────────

const MOTION_BANNER: Record<string, { bg: string; icon: React.ReactNode; msg: string }> = {
  static: {
    bg: "bg-green-900/40 border-green-700/50",
    icon: <CheckCircle2 size={16} className="text-green-400 shrink-0" />,
    msg: "Camera is stationary — annotate landmarks at any single frame.",
  },
  moderate: {
    bg: "bg-yellow-900/40 border-yellow-700/50",
    icon: <Info size={16} className="text-yellow-400 shrink-0" />,
    msg: "Some camera movement — mark the same landmarks at 2–3 different frames.",
  },
  moving: {
    bg: "bg-red-900/40 border-red-700/50",
    icon: <Wind size={16} className="text-red-400 shrink-0" />,
    msg: "Camera moves significantly — mark landmarks at multiple keyframes (every ~10 s).",
  },
  unknown: {
    bg: "bg-slate-700/40 border-slate-600/50",
    icon: <Info size={16} className="text-slate-400 shrink-0" />,
    msg: "Annotate landmarks at the frame that best shows the court.",
  },
};

// ── Court diagram SVG ─────────────────────────────────────────────────────────

function CourtDiagram({
  catalog,
  placed,
  selectedLandmarkId,
  onSelect,
}: {
  catalog: LandmarkCatalogItem[];
  placed: LandmarkPoint[];
  selectedLandmarkId: string;
  onSelect: (id: string) => void;
}) {
  const W = 560;
  const H = 300;
  const PAD = 24;
  const cw = W - PAD * 2;
  const ch = H - PAD * 2;

  const cx = (nx: number) => PAD + nx * cw;
  const cy = (ny: number) => PAD + ny * ch;

  // Key dimensions in normalized coords
  const keyDepth = 0.207;
  const keyHalfW = 0.163;
  const threeR = 0.214; // ~6m/28m normalized

  // Placed landmark_ids at the current frame (or any frame)
  const placedIds = new Set(placed.map((p) => p.landmark_id));

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full rounded-xl bg-slate-900 border border-slate-700"
      style={{ maxHeight: 220 }}
    >
      {/* Court outline */}
      <rect x={PAD} y={PAD} width={cw} height={ch} fill="none" stroke="#475569" strokeWidth={1.5} />

      {/* Midline */}
      <line x1={cx(0.5)} y1={cy(0)} x2={cx(0.5)} y2={cy(1)} stroke="#475569" strokeWidth={1} />

      {/* Center circle */}
      <circle cx={cx(0.5)} cy={cy(0.5)} r={ch * 0.12} fill="none" stroke="#475569" strokeWidth={1} />

      {/* Left key */}
      <rect
        x={cx(0)} y={cy(0.5 - keyHalfW)}
        width={cx(keyDepth) - cx(0)} height={ch * keyHalfW * 2}
        fill="none" stroke="#475569" strokeWidth={1}
      />
      {/* Left FT circle */}
      <circle cx={cx(keyDepth)} cy={cy(0.5)} r={ch * 0.12} fill="none" stroke="#475569" strokeWidth={1} strokeDasharray="4 3" />
      {/* Left 3pt arc (approximate) */}
      <path
        d={`M ${cx(0)} ${cy(0.5 - threeR)} A ${cw * threeR} ${cw * threeR} 0 0 1 ${cx(0)} ${cy(0.5 + threeR)}`}
        fill="none" stroke="#475569" strokeWidth={1}
      />
      {/* Left hoop */}
      <circle cx={cx(0.056)} cy={cy(0.5)} r={5} fill="none" stroke="#f472b6" strokeWidth={1.5} />

      {/* Right key */}
      <rect
        x={cx(1 - keyDepth)} y={cy(0.5 - keyHalfW)}
        width={cx(keyDepth) - cx(0)} height={ch * keyHalfW * 2}
        fill="none" stroke="#475569" strokeWidth={1}
      />
      {/* Right FT circle */}
      <circle cx={cx(1 - keyDepth)} cy={cy(0.5)} r={ch * 0.12} fill="none" stroke="#475569" strokeWidth={1} strokeDasharray="4 3" />
      {/* Right 3pt arc */}
      <path
        d={`M ${cx(1)} ${cy(0.5 - threeR)} A ${cw * threeR} ${cw * threeR} 0 0 0 ${cx(1)} ${cy(0.5 + threeR)}`}
        fill="none" stroke="#475569" strokeWidth={1}
      />
      {/* Right hoop */}
      <circle cx={cx(0.944)} cy={cy(0.5)} r={5} fill="none" stroke="#f472b6" strokeWidth={1.5} />

      {/* Landmark dots */}
      {catalog.map((lm) => {
        const pos = COURT_POSITIONS[lm.id];
        if (!pos) return null;
        const [nx, ny] = pos;
        const x = cx(nx);
        const y = cy(ny);
        const color = getCatColor(lm.category);
        const isPlaced = placedIds.has(lm.id);
        const isSelected = lm.id === selectedLandmarkId;

        return (
          <g key={lm.id} onClick={() => onSelect(lm.id)} className="cursor-pointer">
            {isSelected && (
              <circle cx={x} cy={y} r={10} fill={color} fillOpacity={0.25} />
            )}
            <circle
              cx={x} cy={y} r={isSelected ? 6 : 5}
              fill={isPlaced ? color : "transparent"}
              stroke={color}
              strokeWidth={isSelected ? 2.5 : 1.5}
              opacity={isPlaced || isSelected ? 1 : 0.5}
            />
            {/* Label — show for selected or placed */}
            {(isSelected || isPlaced) && (
              <text
                x={x}
                y={y - 9}
                textAnchor="middle"
                fontSize={7}
                fill={color}
                fontWeight={isSelected ? "bold" : "normal"}
              >
                {lm.label.split(" - ").pop()}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

// ── Format time mm:ss ─────────────────────────────────────────────────────────
function fmtTime(s: number) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

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

  // Video playback state
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

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
        if (ann?.landmarks && ann.landmarks.length > 0) setPlaced(ann.landmarks);
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

  // Draw markers on canvas whenever placed landmarks or currentTime change
  useEffect(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!canvas || !video) return;

    canvas.width = video.clientWidth;
    canvas.height = video.clientHeight;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Show landmarks near the current playback time (within 0.5s)
    const visiblePlaced = placed.filter(
      (lm) => Math.abs(lm.frame_t - currentTime) < 0.5 || currentTime === 0
    );

    visiblePlaced.forEach((lm, idx) => {
      const cat = catalog.find((c) => c.id === lm.landmark_id);
      const color = getCatColor(cat?.category ?? "");
      const [x, y] = lm.pixel;
      const isSelected = lm.landmark_id === selectedLandmarkId;

      // Outer ring for selected
      if (isSelected) {
        ctx.beginPath();
        ctx.arc(x, y, 14, 0, Math.PI * 2);
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 3]);
        ctx.stroke();
        ctx.setLineDash([]);
      }

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

      // Label
      ctx.fillStyle = color;
      ctx.font = "bold 11px sans-serif";
      ctx.textAlign = "left";
      ctx.fillText(cat?.label.split(" - ").pop() ?? lm.landmark_id, x + 12, y + 4);
    });
  }, [placed, catalog, currentTime, selectedLandmarkId]);

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

      // Auto-advance to next unplaced landmark
      const currentIdx = catalog.findIndex((c) => c.id === selectedLandmarkId);
      if (currentIdx >= 0 && currentIdx < catalog.length - 1) {
        setSelectedLandmarkId(catalog[currentIdx + 1].id);
      }
    },
    [selectedLandmarkId, catalog]
  );

  // Custom video controls
  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) { v.play(); } else { v.pause(); }
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = Number(e.target.value);
    setCurrentTime(Number(e.target.value));
  };

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
                Pause the video at a clear frame, then click to place each landmark.
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
            {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <CheckCircle2 size={14} /> : <Save size={14} />}
            {saved ? "Guardado!" : `Guardar (${placed.length}/4 min)`}
          </button>
        </div>

        {/* Motion banner */}
        {(motion || detectingMotion) && (
          <div className={clsx(
            "flex items-start gap-3 px-4 py-3 rounded-lg border text-sm",
            detectingMotion ? "bg-slate-700/40 border-slate-600/50 text-slate-400"
              : MOTION_BANNER[motion!]?.bg ?? "bg-slate-700/40 border-slate-600/50"
          )}>
            {detectingMotion
              ? <Loader2 size={16} className="text-slate-400 shrink-0 animate-spin mt-0.5" />
              : <span className="mt-0.5">{MOTION_BANNER[motion!]?.icon}</span>}
            <span className="text-slate-200">
              {detectingMotion ? "Detecting camera motion…" : MOTION_BANNER[motion!]?.msg}
            </span>
          </div>
        )}

        {saveError && (
          <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-red-900/30 border border-red-700/50 text-sm text-red-300">
            <AlertCircle size={14} /> {saveError}
          </div>
        )}

        {/* Main layout */}
        <div className="flex gap-4">
          {/* Left: video + controls + court diagram */}
          <div className="flex-1 min-w-0 space-y-3">
            {/* Video + canvas overlay */}
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
                    className="w-full h-full object-contain"
                    onLoadedMetadata={() => {
                      setDuration(videoRef.current?.duration ?? 0);
                      handleVideoLoaded();
                    }}
                    onTimeUpdate={() => setCurrentTime(videoRef.current?.currentTime ?? 0)}
                    onPlay={() => setIsPlaying(true)}
                    onPause={() => setIsPlaying(false)}
                  />
                  <canvas
                    ref={canvasRef}
                    onClick={handleCanvasClick}
                    className="absolute inset-0 w-full h-full"
                    style={{
                      cursor: selectedLandmarkId ? "crosshair" : "default",
                      pointerEvents: selectedLandmarkId ? "auto" : "none",
                    }}
                  />
                </>
              ) : (
                <div className="flex items-center justify-center h-full text-slate-500 gap-2">
                  <Loader2 size={24} className="animate-spin opacity-50" />
                  <p className="text-sm">Cargando video…</p>
                </div>
              )}
            </div>

            {/* Custom video controls */}
            {videoUrl && (
              <div className="bg-slate-800 rounded-xl border border-slate-700 px-4 py-3 space-y-2">
                <div className="flex items-center gap-3">
                  <button
                    onClick={togglePlay}
                    className="p-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-white transition-colors shrink-0"
                  >
                    {isPlaying ? <Pause size={16} /> : <Play size={16} />}
                  </button>
                  <input
                    type="range"
                    min={0}
                    max={duration || 1}
                    step={0.033}
                    value={currentTime}
                    onChange={handleSeek}
                    className="flex-1 h-1.5 accent-blue-500 cursor-pointer"
                  />
                  <span className="text-xs text-slate-400 font-mono shrink-0">
                    {fmtTime(currentTime)} / {fmtTime(duration)}
                  </span>
                </div>
                <p className="text-xs text-slate-500">
                  {selectedLandmarkId
                    ? <>Modo anotación activo — <strong className="text-slate-300">haz clic en el video</strong> para colocar el punto seleccionado</>
                    : "Selecciona un punto en el panel derecho para comenzar a anotar"}
                </p>
              </div>
            )}

            {/* Court diagram */}
            <div className="space-y-2">
              <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wide flex items-center gap-2">
                <MapPin size={12} /> Referencia de cancha
              </h2>
              <CourtDiagram
                catalog={catalog}
                placed={placed}
                selectedLandmarkId={selectedLandmarkId}
                onSelect={setSelectedLandmarkId}
              />
              <p className="text-xs text-slate-500">
                Haz clic en un punto del diagrama para seleccionarlo. Los puntos colocados aparecen rellenos.
              </p>
            </div>
          </div>

          {/* Sidebar */}
          <div className="w-72 shrink-0 flex flex-col gap-4">
            {/* Landmark selector */}
            <div className="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <MapPin size={14} /> Punto a colocar
              </h2>
              <select
                value={selectedLandmarkId}
                onChange={(e) => setSelectedLandmarkId(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {Object.entries(catGroups).map(([cat, items]) => (
                  <optgroup key={cat} label={cat.charAt(0).toUpperCase() + cat.slice(1)}>
                    {items.map((lm) => (
                      <option key={lm.id} value={lm.id}>{lm.label}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
              {selectedLandmarkId && (
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <span
                    className="w-3 h-3 rounded-full shrink-0"
                    style={{ backgroundColor: getCatColor(catalog.find((c) => c.id === selectedLandmarkId)?.category ?? "") }}
                  />
                  Pausa el video y haz clic para colocar
                </div>
              )}
            </div>

            {/* Placed list */}
            <div className="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3 flex-1 overflow-y-auto">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                Puntos colocados
                <span className="ml-auto text-xs font-normal text-slate-400">
                  {placed.length} / min 4
                </span>
              </h2>
              {placed.length === 0 ? (
                <p className="text-xs text-slate-500">
                  Aún no hay puntos. Selecciona uno arriba y haz clic en el video.
                </p>
              ) : (
                <ul className="space-y-1.5">
                  {placed.map((lm, idx) => {
                    const cat = catalog.find((c) => c.id === lm.landmark_id);
                    return (
                      <li
                        key={idx}
                        className={clsx(
                          "flex items-center gap-2 px-2.5 py-2 rounded-lg border text-xs",
                          "bg-slate-700/50",
                          cat ? CAT_RING[cat.category] : "border-slate-600"
                        )}
                      >
                        <span className="w-2.5 h-2.5 rounded-full shrink-0"
                          style={{ backgroundColor: getCatColor(cat?.category ?? "") }} />
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-white truncate">{cat?.label ?? lm.landmark_id}</div>
                          <div className="text-slate-400">
                            [{Math.round(lm.pixel[0])}, {Math.round(lm.pixel[1])}]
                            {lm.frame_t > 0 && <> · {lm.frame_t.toFixed(1)}s</>}
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

            {/* Legend */}
            <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
              <h2 className="text-xs font-semibold text-slate-400 mb-2">Leyenda</h2>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                {Object.entries(CAT_COLORS).map(([cat, color]) => (
                  <div key={cat} className="flex items-center gap-1.5 text-xs text-slate-400">
                    <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
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
