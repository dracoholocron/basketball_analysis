"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import {
  getHoopAnnotation,
  getGameVideoUrl,
  putHoopAnnotation,
  type HoopBox,
} from "@/lib/api";
import {
  AlertCircle, ArrowLeft, Camera, CheckCircle2, Info, Loader2,
  Pause, Play, Save, Target, Trash2,
} from "lucide-react";
import { clsx } from "clsx";

// Distinct color per physical basket (hoop_id). Rim = solid, backboard = dashed,
// so both parts of basket 1/2 share a color but are visually distinguishable.
const HOOP_COLORS = ["#f97316", "#a855f7", "#eab308", "#ec4899"];
function boxColor(h: { kind: string; hoop_id?: number }): string {
  return HOOP_COLORS[(h.hoop_id ?? 0) % HOOP_COLORS.length];
}

function fmtTime(s: number) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function videoContentRect(v: HTMLVideoElement) {
  const cw = v.clientWidth, ch = v.clientHeight;
  const va = v.videoWidth && v.videoHeight ? v.videoWidth / v.videoHeight : cw / ch;
  const ca = cw / ch;
  if (va > ca) { const h = cw / va; return { x: 0, y: (ch - h) / 2, w: cw, h }; }
  const w = ch * va; return { x: (cw - w) / 2, y: 0, w, h: ch };
}

export default function AnnotateHoopPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const [hoops, setHoops] = useState<HoopBox[]>([]);
  const [pending, setPending] = useState<[number, number] | null>(null);
  const [kind, setKind] = useState<"rim" | "backboard">("rim");
  const [hoopId, setHoopId] = useState(0);
  const [hoopCount, setHoopCount] = useState(1);
  const [boxWarn, setBoxWarn] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [videoError, setVideoError] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    if (!id) return;
    getHoopAnnotation(id).then((a) => {
      if (a?.hoops?.length) {
        setHoops(a.hoops);
        const maxId = Math.max(0, ...a.hoops.map((h) => h.hoop_id ?? 0));
        setHoopCount(maxId + 1);
      }
    }).catch(() => null);
    getGameVideoUrl(id).then(setVideoUrl).catch(() => setVideoError(true));
  }, [id]);

  useEffect(() => {
    const canvas = canvasRef.current, video = videoRef.current;
    if (!canvas || !video) return;
    canvas.width = video.clientWidth;
    canvas.height = video.clientHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const cr = videoContentRect(video);
    const toCanvas = (ix: number, iy: number): [number, number] => [
      cr.x + (video.videoWidth ? ix / video.videoWidth * cr.w : 0),
      cr.y + (video.videoHeight ? iy / video.videoHeight * cr.h : 0),
    ];
    hoops.forEach((h) => {
      const [x1, y1] = toCanvas(h.bbox[0], h.bbox[1]);
      const [x2, y2] = toCanvas(h.bbox[2], h.bbox[3]);
      ctx.strokeStyle = boxColor(h);
      ctx.lineWidth = 2.5;
      ctx.setLineDash(h.kind === "backboard" ? [6, 4] : []);  // backboard dashed
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      ctx.setLineDash([]);
      ctx.fillStyle = boxColor(h);
      ctx.font = "bold 12px sans-serif";
      ctx.fillText(`${h.kind === "rim" ? "A" : "T"}${(h.hoop_id ?? 0) + 1}`, x1 + 2, y1 - 4);
    });
    if (pending) {
      const [px, py] = toCanvas(pending[0], pending[1]);
      ctx.fillStyle = boxColor({ kind, hoop_id: hoopId });
      ctx.beginPath(); ctx.arc(px, py, 5, 0, Math.PI * 2); ctx.fill();
    }
  }, [hoops, pending, kind, hoopId, currentTime]);

  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current, v = videoRef.current;
    if (!canvas || !v) return;
    const rect = canvas.getBoundingClientRect();
    const cr = videoContentRect(v);
    const x = (e.clientX - rect.left - cr.x) / cr.w * v.videoWidth;
    const y = (e.clientY - rect.top - cr.y) / cr.h * v.videoHeight;
    if (!pending) {
      setPending([x, y]);
    } else {
      const bbox: [number, number, number, number] = [
        Math.min(pending[0], x), Math.min(pending[1], y),
        Math.max(pending[0], x), Math.max(pending[1], y),
      ];
      // Guard: a box wider than ~30% of the frame almost certainly spans two
      // different hoops (corners clicked on different rims). Reject it.
      const bw = bbox[2] - bbox[0];
      if (bw > v.videoWidth * 0.3) {
        setBoxWarn("Ese recuadro abarca demasiado (de un aro al otro). Marca las DOS esquinas del MISMO aro.");
        setPending(null);
        return;
      }
      setBoxWarn("");
      setHoops((prev) => [...prev, { frame_t: v.currentTime ?? 0, bbox, kind, hoop_id: hoopId }]);
      setPending(null);
    }
  }, [pending, kind, hoopId]);

  const togglePlay = () => { const v = videoRef.current; if (v) { v.paused ? v.play() : v.pause(); } };
  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = videoRef.current; if (!v) return;
    v.currentTime = Number(e.target.value); setCurrentTime(Number(e.target.value));
  };
  const removeHoop = (idx: number) => setHoops((prev) => prev.filter((_, i) => i !== idx));

  const handleSave = async () => {
    if (!id || hoops.length < 1) return;
    setSaving(true); setSaveError(null);
    try {
      await putHoopAnnotation(id, hoops);
      setSaved(true);
      setTimeout(() => router.push(`/games/${id}`), 1000);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Save failed");
    } finally { setSaving(false); }
  };

  return (
    <AppShell>
      <div className="max-w-7xl mx-auto space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link href={`/games/${id}`} className="p-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300">
              <ArrowLeft size={16} />
            </Link>
            <div>
              <h1 className="text-xl font-bold text-white">Anotar aro / tablero</h1>
              <p className="text-sm text-slate-400">
                Haz clic en dos esquinas opuestas para encuadrar el aro (mejora el conteo de tiros).
              </p>
            </div>
          </div>
          <button
            onClick={handleSave}
            disabled={hoops.length < 1 || saving || saved}
            className={clsx(
              "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
              hoops.length >= 1 && !saved ? "bg-blue-600 hover:bg-blue-700 text-white"
                : saved ? "bg-green-600 text-white" : "bg-slate-700 text-slate-400 cursor-not-allowed"
            )}
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <CheckCircle2 size={14} /> : <Save size={14} />}
            {saved ? "Guardado!" : `Guardar (${hoops.length})`}
          </button>
        </div>

        <div className="flex items-start gap-3 px-4 py-3 rounded-lg border bg-slate-700/40 border-slate-600/50 text-sm">
          <Info size={16} className="text-slate-400 shrink-0 mt-0.5" />
          <span className="text-slate-200">
            Pausa el video. Clic en dos esquinas opuestas para encuadrar el <strong>aro</strong> (línea
            sólida) o el <strong>tablero</strong> (línea punteada). Cada recuadro guarda el{" "}
            <strong>tiempo</strong> del frame en que lo marcas.
            <br />
            <strong>Cámara estática:</strong> basta marcar cada canasta una vez.{" "}
            <strong>Cámara en paneo:</strong> marca el <em>mismo</em> aro/tablero varias veces a lo
            largo del video (inicio, medio, fin); el sistema interpola su posición entre esos momentos
            para que siga la cámara.
            <br />
            Si hay <strong>dos canastas</strong>, usa el selector «Canasta 1 / Canasta 2» (cada una con
            su color) para indicar a cuál pertenecen el aro y el tablero. Así no se confunden entre sí.
          </span>
        </div>

        {saveError && (
          <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-red-900/30 border border-red-700/50 text-sm text-red-300">
            <AlertCircle size={14} /> {saveError}
          </div>
        )}
        {boxWarn && (
          <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-amber-900/30 border border-amber-700/50 text-sm text-amber-300">
            <AlertCircle size={14} /> {boxWarn}
          </div>
        )}

        <div className="flex gap-4">
          <div className="flex-1 min-w-0 space-y-3">
            <div className="relative bg-black rounded-xl overflow-hidden" style={{ aspectRatio: "16/9" }}>
              {videoError ? (
                <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-2">
                  <Camera size={48} className="opacity-30" />
                  <p className="text-sm">No se pudo cargar el video</p>
                </div>
              ) : videoUrl ? (
                <>
                  <video
                    ref={videoRef} src={videoUrl} className="w-full h-full object-contain"
                    onLoadedMetadata={() => setDuration(videoRef.current?.duration ?? 0)}
                    onTimeUpdate={() => setCurrentTime(videoRef.current?.currentTime ?? 0)}
                    onPlay={() => setIsPlaying(true)} onPause={() => setIsPlaying(false)}
                  />
                  <canvas ref={canvasRef} onClick={handleCanvasClick}
                    className="absolute inset-0 w-full h-full" style={{ cursor: "crosshair" }} />
                </>
              ) : (
                <div className="flex items-center justify-center h-full text-slate-500 gap-2">
                  <Loader2 size={24} className="animate-spin opacity-50" />
                  <p className="text-sm">Cargando video…</p>
                </div>
              )}
            </div>

            {videoUrl && (
              <div className="bg-slate-800 rounded-xl border border-slate-700 px-4 py-3 space-y-2">
                <div className="flex items-center gap-3">
                  <button onClick={togglePlay} className="p-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-white shrink-0">
                    {isPlaying ? <Pause size={16} /> : <Play size={16} />}
                  </button>
                  <input type="range" min={0} max={duration || 1} step={0.033} value={currentTime}
                    onChange={handleSeek} className="flex-1 h-1.5 accent-orange-500 cursor-pointer" />
                  <span className="text-xs text-slate-400 font-mono shrink-0">{fmtTime(currentTime)} / {fmtTime(duration)}</span>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-slate-400">Tipo:</span>
                  {(["rim", "backboard"] as const).map((k) => (
                    <button key={k} onClick={() => setKind(k)}
                      className={clsx("px-3 py-1 rounded-lg text-xs",
                        kind === k ? "bg-blue-600 text-white" : "bg-slate-700 text-slate-300")}>
                      {k === "rim" ? "Aro" : "Tablero"}
                    </button>
                  ))}
                  <span className="text-xs text-slate-400 ml-2">¿Qué canasta?</span>
                  {Array.from({ length: hoopCount }).map((_, i) => (
                    <button key={i} onClick={() => setHoopId(i)}
                      className={clsx(
                        "px-3 py-1 rounded-lg text-xs font-semibold border",
                        hoopId === i ? "text-white border-transparent" : "bg-slate-700 text-slate-300 border-slate-600",
                      )}
                      style={hoopId === i ? { backgroundColor: HOOP_COLORS[i % HOOP_COLORS.length] } : undefined}>
                      Canasta {i + 1}
                    </button>
                  ))}
                  <button
                    onClick={() => { setHoopCount((c) => c + 1); setHoopId(hoopCount); }}
                    className="px-2 py-1 rounded-lg text-xs bg-slate-700 text-slate-300 hover:text-white"
                    title="Añadir otra canasta">
                    + canasta
                  </button>
                  {pending && <span className="text-xs text-orange-400">esquina 1 marcada — clic en la opuesta</span>}
                </div>
              </div>
            )}
          </div>

          <div className="w-72 shrink-0">
            <div className="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <Target size={14} /> Recuadros ({hoops.length})
              </h2>
              {hoops.length === 0 ? (
                <p className="text-xs text-slate-500">Sin recuadros. Marca dos esquinas del aro.</p>
              ) : (
                <ul className="space-y-1.5">
                  {[...hoops].sort((a, b) => (a.hoop_id ?? 0) - (b.hoop_id ?? 0) || (a.frame_t ?? 0) - (b.frame_t ?? 0)).map((h) => {
                    const idx = hoops.indexOf(h);
                    return (
                    <li key={idx} className="flex items-center gap-2 px-2.5 py-2 rounded-lg border text-xs bg-slate-700/50 border-slate-600">
                      <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: boxColor(h) }} />
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-white">{h.kind === "rim" ? "Aro" : "Tablero"} {(h.hoop_id ?? 0) + 1}</div>
                        <button
                          onClick={() => { const v = videoRef.current; if (v) { v.currentTime = h.frame_t ?? 0; setCurrentTime(h.frame_t ?? 0); } }}
                          className="text-slate-400 hover:text-orange-400 transition-colors"
                          title="Ir a este momento del video"
                        >
                          ⏱ {fmtTime(h.frame_t ?? 0)} · {Math.round(h.bbox[2] - h.bbox[0])}×{Math.round(h.bbox[3] - h.bbox[1])} px
                        </button>
                      </div>
                      <button onClick={() => removeHoop(idx)} className="p-1 rounded text-slate-500 hover:text-red-400 hover:bg-red-900/20">
                        <Trash2 size={12} />
                      </button>
                    </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
