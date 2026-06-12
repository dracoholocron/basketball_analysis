"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import VideoControls from "@/components/video/VideoControls";
import {
  analyzeGame,
  getBallAnnotation,
  getBallSession,
  startBallSession,
  pauseBallSession,
  resumeBallSession,
  cancelBallSession,
  getGameVideoUrl,
  putBallAnnotation,
  type BallPoint,
  type BallFlaggedSegment,
  type BallSession,
} from "@/lib/api";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Ban,
  Camera,
  CheckCircle2,
  ChevronRight,
  EyeOff,
  Info,
  Loader2,
  Pause,
  Play,
  PlayCircle,
  Save,
  Square,
  Target,
  Trash2,
  Zap,
} from "lucide-react";
import { clsx } from "clsx";

const BALL_COLOR = "#f97316";  // orange — the ball
const WRONG_COLOR = "#ef4444"; // red — wrong object (negative prompt)
const SESSION_ACTIVE = new Set(["queued", "running"]);

function fmtTime(s: number) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

// Rect actually covered by the video under CSS object-contain (handles
// letterbox/pillarbox on non-16:9 video so clicks map to true intrinsic pixels).
function videoContentRect(v: HTMLVideoElement) {
  const cw = v.clientWidth, ch = v.clientHeight;
  const va = v.videoWidth && v.videoHeight ? v.videoWidth / v.videoHeight : cw / ch;
  const ca = cw / ch;
  if (va > ca) { const h = cw / va; return { x: 0, y: (ch - h) / 2, w: cw, h }; }
  const w = ch * va; return { x: (cw - w) / 2, y: 0, w, h: ch };
}

export default function AnnotateBallPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const [points, setPoints] = useState<BallPoint[]>([]);
  const [mode, setMode] = useState<"ball" | "wrong">("ball");
  const [flagged, setFlagged] = useState<BallFlaggedSegment[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [videoError, setVideoError] = useState(false);

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  // ── Interactive ball-tracking session ──────────────────────────────────────
  const [session, setSession] = useState<BallSession | null>(null);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [analyzingCurated, setAnalyzingCurated] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);


  const stopPoll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  const startPoll = useCallback((gameId: string) => {
    stopPoll();
    pollRef.current = setInterval(async () => {
      try {
        const s = await getBallSession(gameId);
        setSession(s);
        if (s && !SESSION_ACTIVE.has(s.status)) stopPoll();
      } catch { /* ignore */ }
    }, 2000);
  }, []);

  useEffect(() => () => stopPoll(), []);

  // Seek video to the pause frame so the user can correct right there
  useEffect(() => {
    if (session?.status === "waiting_user" && session.pause_frame != null && videoRef.current) {
      const t = session.pause_frame / Math.max(session.fps, 1);
      videoRef.current.currentTime = t;
      setCurrentTime(t);
    }
  }, [session?.status, session?.pause_frame, session?.fps]);

  const handleStartSession = async () => {
    if (!id) return;
    setSessionError(null);
    setSessionLoading(true);
    try {
      const s = await startBallSession(id);
      setSession(s);
      startPoll(id);
    } catch (e: unknown) {
      setSessionError(e instanceof Error ? e.message : "Error al iniciar");
    } finally {
      setSessionLoading(false);
    }
  };

  const handlePauseSession = async () => {
    if (!id) return;
    try { const s = await pauseBallSession(id); setSession(s); }
    catch { /* ignore */ }
  };

  const handleResumeSession = async () => {
    if (!id) return;
    setSessionError(null);
    setSessionLoading(true);
    try {
      const s = await resumeBallSession(id);
      setSession(s);
      startPoll(id);
    } catch (e: unknown) {
      setSessionError(e instanceof Error ? e.message : "Error al reanudar");
    } finally {
      setSessionLoading(false);
    }
  };

  const handleCancelSession = async () => {
    if (!id) return;
    try { const s = await cancelBallSession(id); setSession(s); stopPoll(); }
    catch { /* ignore */ }
  };

  const handleAnalyzeCurated = async () => {
    if (!id) return;
    setAnalyzingCurated(true);
    try {
      await analyzeGame(id, { use_curated_ball: true });
      router.push(`/games/${id}`);
    } catch (e: unknown) {
      setSessionError(e instanceof Error ? e.message : "Error al lanzar análisis");
      setAnalyzingCurated(false);
    }
  };

  useEffect(() => {
    if (!id) return;
    getBallAnnotation(id)
      .then((ann) => {
        if (ann?.points && ann.points.length > 0) setPoints(ann.points);
        if (ann?.flagged && ann.flagged.length > 0) setFlagged(ann.flagged);
      })
      .catch(() => null);
    // Load latest session status
    getBallSession(id).then((s) => {
      setSession(s);
      if (s && SESSION_ACTIVE.has(s.status)) startPoll(id);
    }).catch(() => null);
    getGameVideoUrl(id)
      .then((url) => setVideoUrl(url))
      .catch(() => setVideoError(true));
  }, [id, startPoll]);

  // Draw the ball mark near the current time
  useEffect(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!canvas || !video) return;

    canvas.width = video.clientWidth;
    canvas.height = video.clientHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const cr = videoContentRect(video);

    points
      .filter((p) => Math.abs(p.frame_t - currentTime) < 0.4)
      .forEach((p) => {
        if (!p.visible && !p.negative) return; // "not visible" has no on-screen position
        const x = cr.x + (video.videoWidth ? p.pixel[0] / video.videoWidth * cr.w : 0);
        const y = cr.y + (video.videoHeight ? p.pixel[1] / video.videoHeight * cr.h : 0);
        const color = p.negative ? WRONG_COLOR : BALL_COLOR;
        ctx.strokeStyle = color;
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.arc(x, y, 10, 0, Math.PI * 2);
        ctx.stroke();
        if (p.negative) {
          // X mark: "this object is NOT the ball"
          ctx.beginPath();
          ctx.moveTo(x - 6, y - 6); ctx.lineTo(x + 6, y + 6);
          ctx.moveTo(x + 6, y - 6); ctx.lineTo(x - 6, y + 6);
          ctx.stroke();
        } else {
          ctx.beginPath();
          ctx.arc(x, y, 2.5, 0, Math.PI * 2);
          ctx.fillStyle = color;
          ctx.fill();
        }
      });
  }, [points, currentTime]);

  // Click → mark the ball at the current frame (intrinsic coords)
  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    const v = videoRef.current;
    if (!canvas || !v) return;
    const rect = canvas.getBoundingClientRect();
    const cr = videoContentRect(v);
    const x = (e.clientX - rect.left - cr.x) / cr.w * v.videoWidth;
    const y = (e.clientY - rect.top - cr.y) / cr.h * v.videoHeight;
    const frame_t = v.currentTime ?? 0;

    setPoints((prev) => {
      const isNeg = mode === "wrong";
      const pt: BallPoint = { frame_t, pixel: [x, y], visible: true, negative: isNeg };
      // Positives and negatives coexist on the same frame (ball here + wrong object
      // there); replace only a point of the SAME kind near this time.
      const i = prev.findIndex(
        (p) => Math.abs(p.frame_t - frame_t) < 0.4 && !!p.negative === isNeg,
      );
      if (i >= 0) {
        const next = [...prev];
        next[i] = pt;
        return next;
      }
      return [...prev, pt].sort((a, b) => a.frame_t - b.frame_t);
    });
  }, [mode]);

  const markNotVisible = () => {
    const v = videoRef.current;
    if (!v) return;
    const frame_t = v.currentTime ?? 0;
    setPoints((prev) => {
      const i = prev.findIndex((p) => Math.abs(p.frame_t - frame_t) < 0.4);
      const pt: BallPoint = { frame_t, pixel: [0, 0], visible: false };
      if (i >= 0) {
        const next = [...prev];
        next[i] = pt;
        return next;
      }
      return [...prev, pt].sort((a, b) => a.frame_t - b.frame_t);
    });
  };

  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) v.play();
    else v.pause();
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = Number(e.target.value);
    setCurrentTime(Number(e.target.value));
  };

  const removePoint = (idx: number) =>
    setPoints((prev) => prev.filter((_, i) => i !== idx));

  const handleSave = async () => {
    if (!id || points.length < 1) return;
    setSaving(true);
    setSaveError(null);
    try {
      await putBallAnnotation(id, points);
      setSaved(true);
      setTimeout(() => router.push(`/games/${id}`), 1000);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const visibleCount = points.filter((p) => p.visible && !p.negative).length;
  const negativeCount = points.filter((p) => p.negative).length;

  return (
    <AppShell>
      <div className="max-w-7xl mx-auto space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link href={`/games/${id}`} className="p-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300">
              <ArrowLeft size={16} />
            </Link>
            <div>
              <h1 className="text-xl font-bold text-white">Anotar balón</h1>
              <p className="text-sm text-slate-400">
                Marca el balón en varios momentos; SAM2 lo rastrea por todo el video.
              </p>
            </div>
          </div>
          <button
            onClick={handleSave}
            disabled={points.length < 1 || saving || saved}
            className={clsx(
              "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors",
              points.length >= 1 && !saved
                ? "bg-blue-600 hover:bg-blue-700 text-white"
                : saved
                ? "bg-green-600 text-white"
                : "bg-slate-700 text-slate-400 cursor-not-allowed"
            )}
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <CheckCircle2 size={14} /> : <Save size={14} />}
            {saved ? "Guardado!" : `Guardar (${points.length})`}
          </button>
        </div>

        {/* Guidance */}
        <div className="flex items-start gap-3 px-4 py-3 rounded-lg border bg-slate-700/40 border-slate-600/50 text-sm">
          <Info size={16} className="text-slate-400 shrink-0 mt-0.5" />
          <span className="text-slate-200">
            Pausa el video y <strong className="text-orange-400">haz clic en el balón</strong>.
            Marca ~1 cada 5-10 s y siempre que cambie de manos o dirección (recomendado ≥5).
            Si el balón no se ve en un momento, usa <strong>&quot;Balón no visible&quot;</strong>.
          </span>
        </div>

        {saveError && (
          <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-red-900/30 border border-red-700/50 text-sm text-red-300">
            <AlertCircle size={14} /> {saveError}
          </div>
        )}

        <div className="flex gap-4">
          {/* Video + canvas */}
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
                    ref={videoRef}
                    src={videoUrl}
                    className="w-full h-full object-contain"
                    onLoadedMetadata={() => setDuration(videoRef.current?.duration ?? 0)}
                    onTimeUpdate={() => setCurrentTime(videoRef.current?.currentTime ?? 0)}
                    onPlay={() => setIsPlaying(true)}
                    onPause={() => setIsPlaying(false)}
                  />
                  <canvas
                    ref={canvasRef}
                    onClick={handleCanvasClick}
                    className="absolute inset-0 w-full h-full"
                    style={{ cursor: "crosshair" }}
                  />
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
                  <input
                    type="range" min={0} max={duration || 1} step={0.033} value={currentTime}
                    onChange={handleSeek}
                    className="flex-1 h-1.5 accent-orange-500 cursor-pointer"
                  />
                  <span className="text-xs text-slate-400 font-mono shrink-0">
                    {fmtTime(currentTime)} / {fmtTime(duration)}
                  </span>
                </div>
                <VideoControls videoRef={videoRef} />
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-slate-400">Clic marca:</span>
                  <div className="flex items-center gap-1 bg-slate-900 rounded-lg p-1">
                    <button onClick={() => setMode("ball")}
                      className={clsx("flex items-center gap-1.5 px-3 py-1 text-xs rounded-md transition-colors",
                        mode === "ball" ? "bg-orange-600 text-white" : "text-slate-400 hover:text-white")}>
                      <Target size={12} /> Balón
                    </button>
                    <button onClick={() => setMode("wrong")}
                      title="Marca un objeto que SAM2 rastreó por error (zapato, silla…): le dice al modelo que eso NO es el balón"
                      className={clsx("flex items-center gap-1.5 px-3 py-1 text-xs rounded-md transition-colors",
                        mode === "wrong" ? "bg-red-600 text-white" : "text-slate-400 hover:text-white")}>
                      <Ban size={12} /> Objeto incorrecto
                    </button>
                  </div>
                  <button
                    onClick={markNotVisible}
                    className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs"
                  >
                    <EyeOff size={13} /> Balón no visible en este frame
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Sidebar — session + review flags + marks list */}
          <div className="w-72 shrink-0 flex flex-col gap-4">

            {/* ── Interactive tracking session panel ──────────────────────── */}
            <div className="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <Zap size={14} className="text-orange-400" /> Tracking interactivo
              </h2>

              {sessionError && (
                <p className="text-[11px] text-red-400 bg-red-900/20 rounded-lg px-2 py-1.5">
                  {sessionError}
                </p>
              )}

              {/* No session yet or cancelled */}
              {(!session || session.status === "cancelled") && (
                <div className="space-y-2">
                  <p className="text-[11px] text-slate-400">
                    SAM2 rastrea el balón frame a frame. Pausa automática si lo pierde; tú
                    corriges y continúas desde ese punto, sin re-analizar el video completo.
                  </p>
                  <button
                    onClick={handleStartSession}
                    disabled={sessionLoading || points.filter(p => p.visible && !p.negative).length < 1}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-orange-600 hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-medium"
                  >
                    {sessionLoading ? <Loader2 size={13} className="animate-spin" /> : <PlayCircle size={13} />}
                    Iniciar tracking interactivo
                  </button>
                  {points.filter(p => p.visible && !p.negative).length < 1 && (
                    <p className="text-[10px] text-amber-400">Añade al menos 1 marca de balón primero.</p>
                  )}
                </div>
              )}

              {/* Running / queued */}
              {session && SESSION_ACTIVE.has(session.status) && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-slate-300 flex items-center gap-1.5">
                      <Loader2 size={11} className="animate-spin text-orange-400" />
                      {session.status === "queued" ? "En cola…" : "Analizando…"}
                    </span>
                    <span className="text-slate-400">
                      {session.coverage_pct.toFixed(1)}% cobertura
                    </span>
                  </div>
                  {session.total_frames > 0 && (
                    <div className="w-full h-1.5 bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-orange-500 transition-all duration-500"
                        style={{ width: `${Math.round(100 * session.current_frame / session.total_frames)}%` }}
                      />
                    </div>
                  )}
                  {session.preview_url && (
                    // Cache-bust with timestamp so the browser reloads the fixed key
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={`${session.preview_url}&_t=${Date.now()}`}
                      alt="preview"
                      className="w-full rounded-lg object-contain bg-black"
                    />
                  )}
                  <div className="text-[10px] text-slate-500 text-center">
                    {session.current_frame} / {session.total_frames} frames
                    {session.fps > 0 && ` · ${fmtTime(session.current_frame / session.fps)}`}
                  </div>
                  <button
                    onClick={handlePauseSession}
                    className="w-full flex items-center justify-center gap-2 px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs"
                  >
                    <Square size={11} /> Pausar
                  </button>
                </div>
              )}

              {/* Waiting for user correction */}
              {session?.status === "waiting_user" && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-[11px] text-amber-300">
                    <AlertTriangle size={11} />
                    {session.pause_reason === "lost"
                      ? "Balón perdido — el modelo no lo encontró"
                      : session.pause_reason === "drift"
                      ? "Posible drift — SAM2 puede estar rastreando el objeto incorrecto"
                      : "Pausado manualmente"}
                  </div>
                  {session.preview_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={session.preview_url}
                      alt="preview en pausa"
                      className="w-full rounded-lg object-contain bg-black"
                    />
                  )}
                  {session.pause_frame != null && (
                    <p className="text-[10px] text-slate-400 text-center">
                      Frame {session.pause_frame} · {fmtTime(session.pause_frame / Math.max(session.fps, 1))}
                      {" "}(el video ya saltó ahí)
                    </p>
                  )}
                  <p className="text-[11px] text-slate-300">
                    Corrige con los modos <strong>Balón</strong> /&nbsp;
                    <strong>Objeto incorrecto</strong> en este frame, luego:
                  </p>
                  <button
                    onClick={handleResumeSession}
                    disabled={sessionLoading}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-orange-600 hover:bg-orange-700 disabled:opacity-50 text-white text-xs font-medium"
                  >
                    {sessionLoading ? <Loader2 size={13} className="animate-spin" /> : <ChevronRight size={13} />}
                    Continuar desde aquí
                  </button>
                  <button
                    onClick={handleCancelSession}
                    className="w-full flex items-center justify-center gap-2 px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-red-900/40 text-slate-400 hover:text-red-400 text-xs"
                  >
                    Cancelar sesión
                  </button>
                </div>
              )}

              {/* Done */}
              {session?.status === "done" && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-[11px] text-green-400">
                    <CheckCircle2 size={11} />
                    Tracking completado · {session.coverage_pct.toFixed(1)}% cobertura
                  </div>
                  {session.preview_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={session.preview_url} alt="preview final" className="w-full rounded-lg object-contain bg-black" />
                  )}
                  <button
                    onClick={handleAnalyzeCurated}
                    disabled={analyzingCurated}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white text-xs font-medium"
                  >
                    {analyzingCurated ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
                    Analizar con track curado
                  </button>
                  <button
                    onClick={handleStartSession}
                    disabled={sessionLoading}
                    className="w-full flex items-center justify-center gap-2 px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs"
                  >
                    Reiniciar sesión
                  </button>
                </div>
              )}

              {/* Error */}
              {session?.status === "error" && (
                <div className="space-y-2">
                  <p className="text-[11px] text-red-400">{session.error_message ?? "Error desconocido"}</p>
                  <button
                    onClick={handleStartSession}
                    disabled={sessionLoading}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-white text-xs"
                  >
                    {sessionLoading ? <Loader2 size={13} className="animate-spin" /> : <PlayCircle size={13} />}
                    Reintentar
                  </button>
                </div>
              )}
            </div>
            {/* ────────────────────────────────────────────────────────────── */}

            {flagged.length > 0 && (
              <div className="bg-amber-900/20 rounded-xl border border-amber-700/40 p-4 space-y-2">
                <h2 className="text-sm font-semibold text-amber-300 flex items-center gap-2">
                  <AlertTriangle size={14} /> Segmentos a revisar ({flagged.length})
                </h2>
                <p className="text-[11px] text-amber-200/70">
                  Posible drift de SAM2 (objeto incorrecto) en el último análisis. Salta al
                  momento, y si rastreó algo que no es el balón, márcalo con
                  <strong> Objeto incorrecto</strong> (y re-marca el balón si se ve).
                </p>
                <ul className="space-y-1">
                  {flagged.map((s, i) => (
                    <li key={i}>
                      <button
                        className="w-full text-left text-xs px-2 py-1.5 rounded-lg bg-amber-900/30 hover:bg-amber-800/40 text-amber-100"
                        onClick={() => {
                          if (videoRef.current) {
                            videoRef.current.pause();
                            videoRef.current.currentTime = s.start_s;
                            setCurrentTime(s.start_s);
                          }
                        }}
                      >
                        ▶ {fmtTime(s.start_s)} – {fmtTime(s.end_s)}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3 flex-1 overflow-y-auto">
              <h2 className="text-sm font-semibold text-white flex items-center gap-2">
                <Target size={14} /> Marcas del balón
                <span className="ml-auto text-xs font-normal text-slate-400">
                  {visibleCount} balón · {negativeCount} incorr. · {points.length - visibleCount - negativeCount} no vis
                </span>
              </h2>
              {points.length === 0 ? (
                <p className="text-xs text-slate-500">
                  Sin marcas aún. Pausa y haz clic en el balón.
                </p>
              ) : (
                <ul className="space-y-1.5">
                  {points.map((p, idx) => (
                    <li
                      key={idx}
                      className="flex items-center gap-2 px-2.5 py-2 rounded-lg border text-xs bg-slate-700/50 border-slate-600"
                    >
                      <span
                        className="w-2.5 h-2.5 rounded-full shrink-0"
                        style={{ backgroundColor: p.negative ? WRONG_COLOR : p.visible ? BALL_COLOR : "#64748b" }}
                      />
                      <div className="flex-1 min-w-0">
                        <button
                          className="font-medium text-white truncate hover:text-orange-400"
                          onClick={() => {
                            if (videoRef.current) {
                              videoRef.current.currentTime = p.frame_t;
                              setCurrentTime(p.frame_t);
                            }
                          }}
                        >
                          {p.frame_t.toFixed(1)}s
                        </button>
                        <div className="text-slate-400">
                          {p.negative
                            ? "objeto incorrecto"
                            : p.visible
                            ? `[${Math.round(p.pixel[0])}, ${Math.round(p.pixel[1])}]`
                            : "no visible"}
                        </div>
                      </div>
                      <button
                        onClick={() => removePoint(idx)}
                        className="p-1 rounded text-slate-500 hover:text-red-400 hover:bg-red-900/20"
                      >
                        <Trash2 size={12} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
