"use client";
import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import {
  getGame,
  uploadVideo,
  getGameMetrics,
  pollJobUntilDone,
  getLatestDoneJobForGame,
  getLatestActiveJobForGame,
  api,
} from "@/lib/api";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") + "/api/v1";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import {
  Activity, AlertCircle, CheckCircle2, Film, Loader2, Target, Upload, Zap,
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
  const [hasActiveJob, setHasActiveJob] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!id) return;
    getGame(id).then(setGame);
    getGameMetrics(id).then(setMetrics).catch(() => null);
    api.get(`/games/${id}/cv-events`).then(r => setCvEvents(r.data ?? [])).catch(() => null);
  }, [id]);

  // Auto-load the last completed job so the video player shows on page load
  useEffect(() => {
    if (!id) return;
    getLatestDoneJobForGame(id)
      .then(j => {
        if (j) {
          setJobStatus({
            id: (j as { id: string }).id,
            status: "done",
            progress_pct: 100,
            current_stage: (j as { current_stage: string }).current_stage,
          });
        }
      })
      .catch(() => null);
    // Also check for an in-flight job to disable the Analizar button
    getLatestActiveJobForGame(id)
      .then(j => setHasActiveJob(!!j))
      .catch(() => null);
  }, [id]);

  async function handleUpload() {
    const file = fileRef.current?.files?.[0];
    if (!file || !id) return;
    setUploading(true);
    try {
      const job = await uploadVideo(id, file);
      setJobStatus({ status: job.status, progress_pct: 0, current_stage: job.current_stage, id: job.id });
      await pollJobUntilDone(job.id, (j) => {
        setJobStatus({ ...j, id: job.id });
      }).catch((err: Error) => {
        setJobStatus(prev => prev ? { ...prev, status: "failed", error_message: err.message } : prev);
      });
      const [m, events] = await Promise.all([
        getGameMetrics(id),
        api.get(`/games/${id}/cv-events`).then(r => r.data ?? []).catch(() => []),
      ]);
      setMetrics(m);
      setCvEvents(events);
    } catch (err) {
      console.error(err);
    } finally {
      setUploading(false);
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
            <div className="flex flex-col gap-2">
              <input ref={fileRef} type="file" accept="video/*" className="hidden" id="video-input" />
              <div className="flex gap-2">
                <label htmlFor="video-input" className="flex items-center gap-1 px-3 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm cursor-pointer">
                  <Upload size={14} /> Elegir video
                </label>
                <button
                  className="flex items-center gap-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium disabled:opacity-50"
                  onClick={handleUpload}
                  disabled={uploading || hasActiveJob}
                  title={hasActiveJob ? "Ya hay un análisis en progreso para este partido" : undefined}
                >
                  {uploading ? <Loader2 size={14} className="animate-spin" /> : <Activity size={14} />}
                  {uploading ? "Procesando…" : jobStatus?.status === "done" ? "Re-analizar" : "Analizar"}
                </button>
              </div>
              {hasActiveJob && !uploading && (
                <p className="text-xs text-amber-400">Análisis en progreso…</p>
              )}
            </div>
          </div>
        </div>

        {/* Job progress / video player */}
        {jobStatus && (
          <div className="bg-slate-800 rounded-xl border border-slate-700 px-5 py-4 text-sm">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-white capitalize flex items-center gap-2">
                {jobStatus.status === "done"    && <CheckCircle2 size={16} className="text-green-400" />}
                {jobStatus.status === "failed"  && <AlertCircle  size={16} className="text-red-400" />}
                {jobStatus.status === "running" && <Loader2 size={16} className="text-blue-400 animate-spin" />}
                {jobStatus.status === "done" ? "Análisis completado" : jobStatus.status}
              </span>
              <span className="text-slate-400">{jobStatus.progress_pct}%</span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-slate-700 overflow-hidden">
              <div
                className="h-full rounded-full bg-blue-500 transition-all duration-500"
                style={{ width: `${jobStatus.progress_pct}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-slate-400 capitalize">
              {jobStatus.current_stage?.replace(/_/g, " ")}
            </p>
            {jobStatus.status === "failed" && jobStatus.error_message && (
              <p className="mt-2 text-xs text-red-400 bg-red-900/20 rounded px-2 py-1">
                {jobStatus.error_message}
              </p>
            )}
            {/* Inline video player — shown when analysis is complete */}
            {jobStatus.status === "done" && jobStatus.id && (
              <div className="mt-4">
                <video
                  controls
                  className="w-full rounded-lg bg-black"
                  src={`${API_BASE}/jobs/${jobStatus.id}/annotated-video`}
                >
                  Tu navegador no soporta la reproducción de video.
                </video>
                <a
                  href={`${API_BASE}/jobs/${jobStatus.id}/annotated-video`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300"
                >
                  <Film size={12} /> Descargar video anotado
                </a>
              </div>
            )}
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
