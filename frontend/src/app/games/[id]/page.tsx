"use client";
import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import {
  getGame,
  uploadVideo,
  analyzeGame,
  hasGameVideo,
  getGameMetrics,
  pollJobUntilDone,
  getLatestDoneJobForGame,
  getLatestActiveJobForGame,
  getGameAnnotation,
  deleteJob,
  api,
} from "@/lib/api";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") + "/api/v1";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import {
  Activity, AlertCircle, CheckCircle2, Crosshair, Film, Loader2, Target, Upload, X, Zap,
} from "lucide-react";
import { clsx } from "clsx";

interface PlayerMetric {
  track_id: number;
  display_label?: string | null;
  team_id: number | null;
  total_distance_m: number;
  avg_speed_kmh: number;
  max_speed_kmh: number;
  possession_frames: number;
  passes_made: number;
  interceptions_made: number;
}

interface Metrics {
  total_frames: number;
  team1_possession_pct: number;
  team2_possession_pct: number;
  team1_passes: number;
  team2_passes: number;
  team1_interceptions: number;
  team2_interceptions: number;
  players: PlayerMetric[];
}

interface CvEvent {
  type: string;
  frame: number;
  track_id?: number;
  confidence?: number;
}

const TEAM_COLORS = ["#3b82f6", "#ef4444"];

const CV_EVENT_CONFIG: Record<string, { color: string; bg: string; icon: React.ReactNode; label: string }> = {
  shot_attempt: { color: "text-orange-400", bg: "bg-orange-500/20 border-orange-500/30", icon: <Target size={14} />, label: "Tiro" },
  rebound:      { color: "text-blue-400",   bg: "bg-blue-500/20 border-blue-500/30",   icon: <Activity size={14} />, label: "Rebote" },
  steal:        { color: "text-purple-400", bg: "bg-purple-500/20 border-purple-500/30", icon: <Zap size={14} />, label: "Robo" },
};

type Tab = "stats" | "events" | "players";

export default function GameDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [game, setGame] = useState<Record<string, unknown> | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [cvEvents, setCvEvents] = useState<CvEvent[]>([]);
  const [activeTab, setActiveTab] = useState<Tab>("stats");
  const [jobStatus, setJobStatus] = useState<{
    status: string;
    progress_pct: number;
    current_stage: string;
    id?: string;
    error_message?: string | null;
  } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [hasActiveJob, setHasActiveJob] = useState(false);
  const [videoReady, setVideoReady] = useState(false);
  const [annotationStatus, setAnnotationStatus] = useState<"none" | "partial" | "done">("none");
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [annotatedVideoUrl, setAnnotatedVideoUrl] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!id) return;
    getGame(id).then(setGame);
    getGameMetrics(id).then(setMetrics).catch(() => null);
    api.get(`/games/${id}/cv-events`).then(r => setCvEvents(r.data ?? [])).catch(() => null);
  }, [id]);

  // Hydrate page state on load
  useEffect(() => {
    if (!id) return;

    // Show completed analysis video if available
    getLatestDoneJobForGame(id)
      .then(j => {
        if (j) {
          const jobId = (j as { id: string }).id;
          setJobStatus({
            id: jobId,
            status: "done",
            progress_pct: 100,
            current_stage: (j as { current_stage: string }).current_stage,
          });
          // Fetch the public presigned URL for the annotated video
          api.get<{ url: string }>(`/jobs/${jobId}/annotated-video`)
            .then(r => setAnnotatedVideoUrl(r.data.url))
            .catch(() => null);
        }
      })
      .catch(() => null);

    // Check for any in-flight job
    getLatestActiveJobForGame(id)
      .then(j => {
        if (j) {
          setHasActiveJob(true);
          // Poll until it completes so the user sees live progress
          const jj = j as { id: string; status: string; progress_pct: number; current_stage: string };
          setJobStatus({ id: jj.id, status: jj.status, progress_pct: jj.progress_pct, current_stage: jj.current_stage });
          setAnalyzing(true);
          pollJobUntilDone(jj.id, (upd) => setJobStatus({ ...upd, id: jj.id }))
            .catch(() => null)
            .finally(() => { setAnalyzing(false); setHasActiveJob(false); });
        }
      })
      .catch(() => null);

    // Detect if a video was already uploaded (enables Annotate Court button)
    hasGameVideo(id)
      .then(v => { if (v) setVideoReady(true); })
      .catch(() => null);

    // Check existing annotation status
    getGameAnnotation(id)
      .then(ann => {
        const n = ann?.landmarks?.length ?? 0;
        if (n >= 4) setAnnotationStatus("done");
        else if (n > 0) setAnnotationStatus("partial");
      })
      .catch(() => null);
  }, [id]);

  async function handleUpload() {
    const file = fileRef.current?.files?.[0];
    if (!file || !id) return;
    setUploading(true);
    try {
      await uploadVideo(id, file);
      setVideoReady(true);
      // Clear the file input so user can pick a different file later
      if (fileRef.current) fileRef.current.value = "";
    } catch (err) {
      console.error(err);
    } finally {
      setUploading(false);
    }
  }

  async function handleDismissJob() {
    setConfirmCancel(false);
    if (!jobStatus?.id) { setJobStatus(null); return; }
    try {
      await deleteJob(jobStatus.id);
    } catch {
      // ignore — might already be deleted
    } finally {
      setJobStatus(null);
      setAnalyzing(false);
      setHasActiveJob(false);
    }
  }

  async function fetchAnnotatedVideoUrl(jobId: string) {
    try {
      const { data } = await api.get<{ url: string }>(`/jobs/${jobId}/annotated-video`);
      setAnnotatedVideoUrl(data.url);
    } catch {
      setAnnotatedVideoUrl(null);
    }
  }

  async function handleAnalyze() {
    if (!id) return;
    setAnalyzing(true);
    setHasActiveJob(true);
    setAnnotatedVideoUrl(null);
    try {
      const job = await analyzeGame(id);
      setJobStatus({ status: job.status, progress_pct: 0, current_stage: job.current_stage, id: job.id });
      await pollJobUntilDone(job.id, (j) => {
        setJobStatus({ ...j, id: job.id });
      }).catch((err: Error) => {
        setJobStatus(prev => prev ? { ...prev, status: "failed", error_message: err.message } : prev);
      });
      await fetchAnnotatedVideoUrl(job.id);
      const [m, events] = await Promise.all([
        getGameMetrics(id),
        api.get(`/games/${id}/cv-events`).then(r => r.data ?? []).catch(() => []),
      ]);
      setMetrics(m);
      setCvEvents(events);
    } catch (err) {
      console.error(err);
    } finally {
      setAnalyzing(false);
      setHasActiveJob(false);
    }
  }

  const possessionData = metrics ? [
    { name: "Team 1", value: metrics.team1_possession_pct },
    { name: "Team 2", value: metrics.team2_possession_pct },
  ] : [];

  const passData = metrics ? [
    { name: "Passes",       team1: metrics.team1_passes,       team2: metrics.team2_passes },
    { name: "Interceptions",team1: metrics.team1_interceptions, team2: metrics.team2_interceptions },
  ] : [];

  const shotCount    = cvEvents.filter(e => e.type === "shot_attempt").length;
  const reboundCount = cvEvents.filter(e => e.type === "rebound").length;
  const stealCount   = cvEvents.filter(e => e.type === "steal").length;

  return (
    <AppShell>
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white">
              {(game?.location as string) ?? "Game Detail"}
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              {(game?.game_date as string) ?? ""}{" "}
              {(game?.court_level as string) && (
                <span className="text-blue-400 font-medium">{game?.court_level as string}</span>
              )}
              {(game?.is_half_court as boolean) && (
                <span className="ml-2 text-amber-400 font-medium">· Half-court</span>
              )}
            </p>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3">
            <Link
              href={`/games/${id}/highlights`}
              className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm font-medium transition-colors"
            >
              <Film size={16} /> Highlights
            </Link>
            {videoReady && (
              <Link
                href={`/games/${id}/annotate`}
                className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm font-medium transition-colors"
              >
                <Crosshair size={16} />
                {annotationStatus === "done"
                  ? "Court annotated"
                  : annotationStatus === "partial"
                  ? "Complete annotation"
                  : "Annotate Court"}
                {annotationStatus === "done" && (
                  <CheckCircle2 size={12} className="text-green-400" />
                )}
              </Link>
            )}
            <div className="flex flex-col gap-2">
              <input ref={fileRef} type="file" accept="video/*" className="hidden" id="video-input" onChange={() => {
                // Show the upload button as active when a file is selected
              }} />
              <div className="flex gap-2 flex-wrap">
                {/* Step 1: Upload */}
                <label
                  htmlFor="video-input"
                  className="flex items-center gap-1 px-3 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm cursor-pointer"
                  title="Cargar un video (sin iniciar análisis)"
                >
                  <Upload size={14} />
                  {uploading ? <Loader2 size={14} className="animate-spin" /> : null}
                  {uploading ? "Cargando…" : videoReady ? "Cambiar video" : "Cargar video"}
                </label>
                <button
                  className="flex items-center gap-1 px-3 py-2 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm disabled:opacity-40"
                  onClick={handleUpload}
                  disabled={uploading}
                  title="Guardar el video seleccionado (sin analizar)"
                >
                  {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
                  {uploading ? "…" : "↑ Subir"}
                </button>
                {/* Step 2: Analyze */}
                <button
                  className="flex items-center gap-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium disabled:opacity-50"
                  onClick={handleAnalyze}
                  disabled={!videoReady || analyzing || hasActiveJob}
                  title={!videoReady ? "Sube un video primero" : hasActiveJob ? "Análisis en progreso" : "Iniciar análisis"}
                >
                  {analyzing ? <Loader2 size={14} className="animate-spin" /> : <Activity size={14} />}
                  {analyzing ? "Analizando…" : jobStatus?.status === "done" ? "Re-analizar" : "Analizar"}
                </button>
              </div>
              {hasActiveJob && !analyzing && (
                <p className="text-xs text-amber-400">Análisis en progreso…</p>
              )}
              {videoReady && !hasActiveJob && annotationStatus === "none" && (
                <p className="text-xs text-blue-400">Tip: anota la cancha antes de analizar para mejor precisión</p>
              )}
            </div>
          </div>
        </div>

        {/* Job progress / video player */}
        {jobStatus && (
          <div className="bg-slate-800 rounded-xl border border-slate-700 px-5 py-4 text-sm space-y-3">
            {/* Header row */}
            <div className="flex items-center justify-between">
              <span className="font-medium text-white flex items-center gap-2">
                {jobStatus.status === "done"    && <CheckCircle2 size={16} className="text-green-400" />}
                {jobStatus.status === "failed"  && <AlertCircle  size={16} className="text-red-400" />}
                {jobStatus.status === "running" && <Loader2 size={16} className="text-blue-400 animate-spin" />}
                {jobStatus.status === "done" ? "Análisis completado" : jobStatus.status === "failed" ? "Falló" : "Analizando…"}
              </span>
              <div className="flex items-center gap-3">
                <span className="text-slate-400 font-mono">{jobStatus.progress_pct}%</span>
                <button
                  onClick={() => setConfirmCancel(true)}
                  title={jobStatus.status === "running" ? "Cancelar análisis" : jobStatus.status === "failed" ? "Descartar error" : "Cerrar"}
                  className="p-1 rounded hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            {/* Progress bar */}
            <div className="h-2 w-full rounded-full bg-slate-700 overflow-hidden">
              <div
                className={clsx(
                  "h-full rounded-full transition-all duration-700",
                  jobStatus.status === "done" ? "bg-green-500" :
                  jobStatus.status === "failed" ? "bg-red-500" : "bg-blue-500"
                )}
                style={{ width: `${jobStatus.progress_pct}%` }}
              />
            </div>

            {/* Stage pipeline steps */}
            {jobStatus.status === "running" && (() => {
              const STAGES = [
                { key: "reading_video",     label: "Leyendo video",        pct: 8  },
                { key: "player_tracking",   label: "Detectando jugadores", pct: 12 },
                { key: "ball_tracking",     label: "Detectando balón",     pct: 30 },
                { key: "keypoint_detection",label: "Keypoints de cancha",  pct: 45 },
                { key: "team_assignment",   label: "Asignando equipos",    pct: 55 },
                { key: "ball_acquisition",  label: "Posesión del balón",   pct: 65 },
                { key: "pass_detection",    label: "Pases e intercepciones",pct: 68},
                { key: "tactical_view",     label: "Vista táctica",        pct: 72 },
                { key: "drawing",           label: "Generando video",      pct: 78 },
                { key: "saving_output",     label: "Guardando resultado",  pct: 85 },
                { key: "persisting_metrics",label: "Guardando métricas",   pct: 92 },
              ];
              const currentIdx = STAGES.findIndex(s => s.key === jobStatus.current_stage);
              return (
                <div className="space-y-1">
                  {STAGES.map((s, i) => {
                    const done = i < currentIdx;
                    const active = i === currentIdx;
                    return (
                      <div key={s.key} className={clsx(
                        "flex items-center gap-2 px-2 py-1 rounded text-xs",
                        active && "bg-blue-500/10 border border-blue-500/30",
                        done && "opacity-50",
                        !done && !active && "opacity-25"
                      )}>
                        {done   && <CheckCircle2 size={11} className="text-green-400 shrink-0" />}
                        {active && <Loader2 size={11} className="text-blue-400 animate-spin shrink-0" />}
                        {!done && !active && <div className="w-[11px] h-[11px] rounded-full border border-slate-600 shrink-0" />}
                        <span className={active ? "text-blue-300 font-medium" : "text-slate-400"}>
                          {s.label}
                        </span>
                        {active && <span className="ml-auto text-blue-400 font-mono">{jobStatus.progress_pct}%</span>}
                      </div>
                    );
                  })}
                </div>
              );
            })()}

            {jobStatus.status === "failed" && jobStatus.error_message && (
              <p className="text-xs text-red-400 bg-red-900/20 rounded px-2 py-1">
                {jobStatus.error_message}
              </p>
            )}

            {/* Inline video player — shown when analysis is complete */}
            {jobStatus.status === "done" && (
              <div>
                {annotatedVideoUrl ? (
                  <>
                    <video
                      controls
                      className="w-full rounded-lg bg-black"
                      src={annotatedVideoUrl}
                    >
                      Tu navegador no soporta la reproducción de video.
                    </video>
                    <a
                      href={annotatedVideoUrl}
                      download
                      className="mt-2 inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300"
                    >
                      <Film size={12} /> Descargar video anotado
                    </a>
                  </>
                ) : (
                  <div className="flex items-center gap-2 text-sm text-slate-400 py-2">
                    <Loader2 size={14} className="animate-spin" />
                    Cargando video…
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Cancel confirmation modal */}
        {confirmCancel && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 max-w-sm w-full mx-4 shadow-2xl space-y-4">
              <div className="flex items-start gap-3">
                <AlertCircle size={22} className="text-amber-400 shrink-0 mt-0.5" />
                <div>
                  <h3 className="font-semibold text-white text-base">
                    {jobStatus?.status === "running" ? "¿Cancelar análisis?" : "¿Descartar resultado?"}
                  </h3>
                  <p className="text-sm text-slate-400 mt-1">
                    {jobStatus?.status === "running"
                      ? "El análisis en curso se detendrá y perderás el progreso actual."
                      : "Se eliminará el registro de este job. Puedes lanzar uno nuevo cuando quieras."}
                  </p>
                </div>
              </div>
              <div className="flex gap-3 justify-end">
                <button
                  onClick={() => setConfirmCancel(false)}
                  className="px-4 py-2 text-sm rounded-lg bg-slate-700 hover:bg-slate-600 text-white transition-colors"
                >
                  Volver
                </button>
                <button
                  onClick={handleDismissJob}
                  className="px-4 py-2 text-sm rounded-lg bg-red-600 hover:bg-red-500 text-white font-medium transition-colors"
                >
                  {jobStatus?.status === "running" ? "Sí, cancelar" : "Descartar"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* CV event summary cards */}
        {cvEvents.length > 0 && (
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: "Tiros", value: shotCount,    icon: <Target size={18} className="text-orange-400" /> },
              { label: "Rebotes", value: reboundCount, icon: <Activity size={18} className="text-blue-400" /> },
              { label: "Robos",   value: stealCount,   icon: <Zap size={18} className="text-purple-400" /> },
            ].map(({ label, value, icon }) => (
              <div key={label} className="bg-slate-800 rounded-xl p-4 flex items-center gap-3">
                {icon}
                <div>
                  <p className="text-xl font-bold text-white">{value}</p>
                  <p className="text-xs text-slate-400">{label}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 bg-slate-800 p-1 rounded-lg w-fit">
          {(["stats", "events", "players"] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={clsx(
                "px-4 py-1.5 text-sm rounded-md transition-colors capitalize",
                activeTab === tab ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white",
              )}
            >
              {tab === "stats" ? "Estadísticas" : tab === "events" ? `Eventos CV${cvEvents.length > 0 ? ` (${cvEvents.length})` : ""}` : "Jugadores"}
            </button>
          ))}
        </div>

        {/* Tab: Stats */}
        {activeTab === "stats" && metrics && (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { label: "Total Frames", value: metrics.total_frames.toLocaleString() },
                { label: "Posesión Equipo 1", value: `${metrics.team1_possession_pct}%` },
                { label: "Posesión Equipo 2", value: `${metrics.team2_possession_pct}%` },
                { label: "Jugadores", value: metrics.players.length },
              ].map(kpi => (
                <div key={kpi.label} className="bg-slate-800 rounded-xl p-5 text-center">
                  <p className="text-3xl font-bold text-blue-400">{kpi.value}</p>
                  <p className="text-sm text-slate-400 mt-1">{kpi.label}</p>
                </div>
              ))}
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <div className="bg-slate-800 rounded-xl p-5">
                <h2 className="text-base font-semibold text-white mb-4">Posesión del balón</h2>
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={possessionData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, value }) => `${name}: ${value}%`}>
                      {possessionData.map((_, i) => <Cell key={i} fill={TEAM_COLORS[i % TEAM_COLORS.length]} />)}
                    </Pie>
                    <Legend /><Tooltip formatter={v => `${v}%`} />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              <div className="bg-slate-800 rounded-xl p-5">
                <h2 className="text-base font-semibold text-white mb-4">Pases e intercepción</h2>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={passData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="name" stroke="#94a3b8" /><YAxis allowDecimals={false} stroke="#94a3b8" />
                    <Tooltip contentStyle={{ background: "#1e293b", border: "none" }} />
                    <Legend />
                    <Bar dataKey="team1" name="Equipo 1" fill={TEAM_COLORS[0]} />
                    <Bar dataKey="team2" name="Equipo 2" fill={TEAM_COLORS[1]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </>
        )}

        {activeTab === "stats" && !metrics && (
          <div className="bg-slate-800 rounded-xl text-center py-20 text-slate-400">
            <Film size={48} className="mx-auto mb-4 opacity-30" />
            <p className="font-medium">Sin análisis aún.</p>
            <p className="text-sm mt-1">Sube un video y haz clic en Analizar.</p>
          </div>
        )}

        {/* Tab: CV Events */}
        {activeTab === "events" && (
          <div className="space-y-2">
            {cvEvents.length === 0 ? (
              <div className="bg-slate-800 rounded-xl text-center py-16 text-slate-400">
                <Activity size={40} className="mx-auto mb-3 opacity-30" />
                <p className="text-sm">No hay eventos CV. Analiza un video con el motor de pose.</p>
              </div>
            ) : (
              cvEvents.map((ev, i) => {
                const cfg = CV_EVENT_CONFIG[ev.type];
                return (
                  <div key={i} className="flex items-center gap-3 bg-slate-800 rounded-lg px-4 py-3">
                    <span className={clsx("flex items-center justify-center w-7 h-7 rounded-full border text-xs", cfg?.bg ?? "bg-slate-700", cfg?.color ?? "text-slate-400")}>
                      {cfg?.icon ?? <Activity size={14} />}
                    </span>
                    <span className="text-white font-medium">{cfg?.label ?? ev.type.replace("_", " ")}</span>
                    {ev.track_id != null && (
                      <span className="text-xs text-slate-500">
                        jugador {metrics?.players.find(p => p.track_id === ev.track_id)?.display_label ?? `#${ev.track_id}`}
                      </span>
                    )}
                    {ev.confidence != null && (
                      <span className="text-xs text-slate-500">{(ev.confidence * 100).toFixed(0)}%</span>
                    )}
                    <span className="text-xs text-slate-500 ml-auto">frame {ev.frame}</span>
                  </div>
                );
              })
            )}
          </div>
        )}

        {/* Tab: Players */}
        {activeTab === "players" && metrics && (
          <div className="bg-slate-800 rounded-xl overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-left text-xs text-slate-400">
                  {["Jugador", "Equipo", "Distancia (m)", "Vel. prom.", "Vel. máx.", "Posesión", "Pases", "Intercep."].map(h => (
                    <th key={h} className="px-4 py-3 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {metrics.players.sort((a, b) => b.total_distance_m - a.total_distance_m).map(p => {
                  const maxSpd = p.max_speed_kmh;
                  const spdColor = maxSpd > 25 ? "text-red-400" : maxSpd > 15 ? "text-amber-400" : "text-green-400";
                  const avgSpd = p.avg_speed_kmh;
                  const avgColor = avgSpd > 20 ? "text-red-400" : avgSpd > 10 ? "text-amber-400" : "text-green-400";
                  const label = p.display_label ?? `#${p.track_id}`;
                  return (
                    <tr key={p.track_id} className="hover:bg-slate-700/50 transition-colors">
                      <td className="px-4 py-3 font-mono font-semibold text-white">{label}</td>
                      <td className="px-4 py-3">
                        <span className="inline-block rounded-full px-2 py-0.5 text-xs font-semibold text-white"
                          style={{ backgroundColor: TEAM_COLORS[(p.team_id ?? 1) - 1] ?? "#6b7280" }}>
                          T{p.team_id ?? "?"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-200">{p.total_distance_m.toFixed(1)}</td>
                      <td className={`px-4 py-3 font-medium ${avgColor}`}>{avgSpd.toFixed(1)} km/h</td>
                      <td className={`px-4 py-3 font-medium ${spdColor}`}>{maxSpd.toFixed(1)} km/h</td>
                      <td className="px-4 py-3 text-slate-200">{p.possession_frames}</td>
                      <td className="px-4 py-3 text-slate-200">{p.passes_made}</td>
                      <td className="px-4 py-3 text-slate-200">{p.interceptions_made}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
  );
}
