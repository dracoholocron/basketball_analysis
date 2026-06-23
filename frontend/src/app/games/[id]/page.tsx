"use client";
import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import VideoControls from "@/components/video/VideoControls";
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
  updateGameSettings,
  getJobSummary,
  correctCvEvent,
  type JobRunSummary,
  api,
} from "@/lib/api";

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import {
  Activity, AlertCircle, CheckCircle2, Crosshair, EyeOff, Film, Loader2,
  Settings2, Target, Upload, Users, X, Zap,
} from "lucide-react";
import { clsx } from "clsx";

interface PlayerMetric {
  track_id: number;
  display_label?: string | null;
  jersey_number?: string | null;
  player_id?: string | null;
  minutes_played?: number;
  team_id: number | null;
  total_distance_m: number;
  avg_speed_kmh: number;
  max_speed_kmh: number;
  possession_frames: number;
  passes_made: number;
  interceptions_made: number;
  shots_attempted?: number;
  shots_made?: number;
  shots_missed?: number;
  rebounds?: number;
}

interface Metrics {
  total_frames: number;
  home_team_name?: string | null;
  away_team_name?: string | null;
  team1_possession_pct: number;
  team2_possession_pct: number;
  team1_passes: number;
  team2_passes: number;
  team1_interceptions: number;
  team2_interceptions: number;
  team1_shots_attempted?: number;
  team2_shots_attempted?: number;
  team1_shots_made?: number;
  team2_shots_made?: number;
  hoop_detected_frames?: number;
  hoops_configured?: number;
  hoops_with_backboard?: number;
  hoops?: { hoop_id: number; team_id: number | null; team_name: string | null; has_backboard: boolean }[];
  players: PlayerMetric[];
}

interface CvEvent {
  idx?: number;
  event_type: string;
  frame: number;
  time_s?: number;
  team_id?: number;
  player_track_id?: number;
  description?: string;
  edited?: boolean;
}

const CV_EVENT_TYPES = ["shot_attempt", "pass", "steal", "rebound", "shot_made", "shot_missed", "turnover", "block"];

const TEAM_COLORS = ["#3b82f6", "#ef4444"];

const CV_EVENT_CONFIG: Record<string, { color: string; bg: string; icon: React.ReactNode; label: string }> = {
  shot_attempt: { color: "text-orange-400", bg: "bg-orange-500/20 border-orange-500/30",   icon: <Target size={14} />,   label: "Tiro" },
  rebound:      { color: "text-blue-400",   bg: "bg-blue-500/20 border-blue-500/30",       icon: <Activity size={14} />, label: "Rebote" },
  steal:        { color: "text-purple-400", bg: "bg-purple-500/20 border-purple-500/30",   icon: <Zap size={14} />,      label: "Robo" },
  pass:         { color: "text-green-400",  bg: "bg-green-500/20 border-green-500/30",     icon: <Activity size={14} />, label: "Pase" },
};

type Tab = "stats" | "events" | "players";

export default function GameDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [game, setGame] = useState<Record<string, unknown> | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [cvEvents, setCvEvents] = useState<CvEvent[]>([]);
  const [activeTab, setActiveTab] = useState<Tab>("stats");
  const [onlyIdentified, setOnlyIdentified] = useState(false);
  const [jobStatus, setJobStatus] = useState<{
    status: string;
    progress_pct: number;
    current_stage: string;
    id?: string;
    error_message?: string | null;
  } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const [analyzing, setAnalyzing] = useState(false);
  const [hasActiveJob, setHasActiveJob] = useState(false);
  const [videoReady, setVideoReady] = useState(false);
  const [annotationStatus, setAnnotationStatus] = useState<"none" | "partial" | "done">("none");
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [annotatedVideoUrl, setAnnotatedVideoUrl] = useState<string | null>(null);
  const [summary, setSummary] = useState<JobRunSummary | null>(null);
  const [eventPopup, setEventPopup] = useState<CvEvent | null>(null);
  const [clipPad, setClipPad] = useState(2);  // seconds before/after the event (configurable)
  const [showAnalyzeModal, setShowAnalyzeModal] = useState(false);
  const [poseFilterInput, setPoseFilterInput] = useState("");
  const [updatingPoses, setUpdatingPoses] = useState(false);
  const [jerseyTeam1, setJerseyTeam1] = useState("");
  const [jerseyTeam2, setJerseyTeam2] = useState("");
  const [teamName1, setTeamName1] = useState("");
  const [teamName2, setTeamName2] = useState("");
  const [gameStartS, setGameStartS] = useState("");
  const [gameEndS, setGameEndS] = useState("");
  const [ballQuality, setBallQuality] = useState<"small" | "base_plus" | "large" | "efficienttam">("base_plus");
  const [ballMode, setBallMode] = useState<"auto" | "tracknet" | "yolo">("auto");
  const fileRef = useRef<HTMLInputElement>(null);
  const annotatedVideoRef = useRef<HTMLVideoElement>(null);

  const showPoses = (game?.show_poses as boolean) ?? true;

  useEffect(() => {
    if (!id) return;
    getGame(id).then(g => {
      setGame(g);
      setJerseyTeam1((g?.home_team1_jersey as string) ?? "white shirt");
      setJerseyTeam2((g?.away_team2_jersey as string) ?? "dark blue shirt");
      setTeamName1((g?.home_team_name as string) ?? "");
      setTeamName2((g?.away_team_name as string) ?? "");
      setGameStartS(g?.analysis_start_s != null ? String(g.analysis_start_s) : "");
      setGameEndS(g?.analysis_end_s != null ? String(g.analysis_end_s) : "");
      setBallQuality(((g?.ball_tracking_quality as "small"|"base_plus"|"large"|"efficienttam") ?? "base_plus"));
      setBallMode(((g?.ball_detector_mode as "auto"|"tracknet"|"yolo") ?? "auto"));
    });
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
          getJobSummary(jobId).then(setSummary).catch(() => null);
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
    setUploadPct(0);
    try {
      await uploadVideo(id, file, (frac) => setUploadPct(Math.round(frac * 100)));
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

  async function handleTogglePoses(value: boolean) {
    if (!id) return;
    setUpdatingPoses(true);
    try {
      const updated = await updateGameSettings(id, { show_poses: value });
      setGame(updated);
    } catch (err) {
      console.error(err);
    } finally {
      setUpdatingPoses(false);
    }
  }

  async function handleAnalyze() {
    if (!id) return;
    setShowAnalyzeModal(false);

    const posePlayerFilter = poseFilterInput.trim()
      ? poseFilterInput.split(",").map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n))
      : undefined;

    // Persist jersey + team-name changes before starting analysis
    const t1 = jerseyTeam1.trim() || "white shirt";
    const t2 = jerseyTeam2.trim() || "dark blue shirt";
    const payload: Record<string, string | number | null> = {};
    if (t1 !== (game?.home_team1_jersey as string)) payload.home_team1_jersey = t1;
    if (t2 !== (game?.away_team2_jersey as string)) payload.away_team2_jersey = t2;
    if (teamName1.trim() && teamName1.trim() !== (game?.home_team_name as string)) payload.home_team_name = teamName1.trim();
    if (teamName2.trim() && teamName2.trim() !== (game?.away_team_name as string)) payload.away_team_name = teamName2.trim();
    payload.analysis_start_s = gameStartS.trim() ? Number(gameStartS) : 0;
    payload.analysis_end_s = gameEndS.trim() ? Number(gameEndS) : null;
    if (ballQuality !== (game?.ball_tracking_quality as string)) payload.ball_tracking_quality = ballQuality;
    if (Object.keys(payload).length > 0) {
      try {
        const updated = await updateGameSettings(id, payload);
        setGame(updated);
      } catch { /* non-fatal */ }
    }

    setAnalyzing(true);
    setHasActiveJob(true);
    setAnnotatedVideoUrl(null);
    try {
      const job = await analyzeGame(id, { pose_player_filter: posePlayerFilter, ball_detector_mode: ballMode });
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
      getJobSummary(job.id).then(setSummary).catch(() => null);
    } catch (err) {
      console.error(err);
    } finally {
      setAnalyzing(false);
      setHasActiveJob(false);
    }
  }

  const chartTeam1 = metrics?.home_team_name || "Local";
  const chartTeam2 = metrics?.away_team_name || "Visitante";
  const possessionData = metrics ? [
    { name: chartTeam1, value: metrics.team1_possession_pct },
    { name: chartTeam2, value: metrics.team2_possession_pct },
  ] : [];

  const passData = metrics ? [
    { name: "Pases",          team1: metrics.team1_passes,        team2: metrics.team2_passes },
    { name: "Intercepciones", team1: metrics.team1_interceptions, team2: metrics.team2_interceptions },
  ] : [];

  const shotCount    = cvEvents.filter(e => e.event_type === "shot_attempt").length;
  const reboundCount = cvEvents.filter(e => e.event_type === "rebound").length;

  // Field-goal shooting from attributed per-player metrics (team-coherent).
  const t1Att = metrics?.team1_shots_attempted ?? 0;
  const t2Att = metrics?.team2_shots_attempted ?? 0;
  const t1Made = metrics?.team1_shots_made ?? 0;
  const t2Made = metrics?.team2_shots_made ?? 0;
  const shotsAttempted = t1Att + t2Att;
  const shotsMade = t1Made + t2Made;
  const fgPct = (m: number, a: number) => (a > 0 ? Math.round((100 * m) / a) : 0);
  const stealCount   = cvEvents.filter(e => e.event_type === "steal").length;

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
            {videoReady && (
              <Link
                href={`/games/${id}/annotate-ball`}
                className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm font-medium transition-colors"
              >
                <Crosshair size={16} />
                Anotar balón
              </Link>
            )}
            {videoReady && (
              <Link
                href={`/games/${id}/annotate-hoop`}
                className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm font-medium transition-colors"
              >
                <Crosshair size={16} />
                Anotar aro
              </Link>
            )}
            {videoReady && (
              <Link
                href={`/games/${id}/annotate-teams`}
                className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm font-medium transition-colors"
              >
                <Users size={16} />
                Anotar equipos
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
                  {uploading ? `Subiendo… ${uploadPct}%` : videoReady ? "Cambiar video" : "Cargar video"}
                </label>
                <button
                  className="flex items-center gap-1 px-3 py-2 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm disabled:opacity-40"
                  onClick={handleUpload}
                  disabled={uploading}
                  title="Guardar el video seleccionado (sin analizar)"
                >
                  {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
                  {uploading ? `${uploadPct}%` : "↑ Subir"}
                </button>
                {/* Step 2: Analyze */}
                <button
                  className="flex items-center gap-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium disabled:opacity-50"
                  onClick={() => setShowAnalyzeModal(true)}
                  disabled={!videoReady || analyzing || hasActiveJob}
                  title={!videoReady ? "Sube un video primero" : hasActiveJob ? "Análisis en progreso" : "Opciones de análisis"}
                >
                  {analyzing ? <Loader2 size={14} className="animate-spin" /> : <Activity size={14} />}
                  {analyzing ? "Analizando…" : jobStatus?.status === "done" ? "Re-analizar" : "Analizar"}
                </button>
              </div>
              {uploading && (
                <div className="w-full max-w-xs">
                  <div className="h-1.5 w-full rounded-full bg-slate-700 overflow-hidden">
                    <div
                      className="h-full bg-blue-500 transition-all duration-200"
                      style={{ width: `${uploadPct}%` }}
                    />
                  </div>
                  <p className="text-xs text-slate-400 mt-1">Subiendo video… {uploadPct}%</p>
                </div>
              )}
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
                      ref={annotatedVideoRef}
                      controls
                      className="w-full rounded-lg bg-black"
                      src={annotatedVideoUrl}
                    >
                      Tu navegador no soporta la reproducción de video.
                    </video>
                    <div className="mt-2">
                      <VideoControls videoRef={annotatedVideoRef} />
                    </div>
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

            {/* Analysis detail: detection-quality proxies + stage timings (per run) */}
            {jobStatus.status === "done" && summary && (
              <div className="mt-4 border-t border-slate-700 pt-4 space-y-3">
                <p className="text-sm font-semibold text-white">Detalle del análisis</p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                  {[
                    ["Cobertura de balón", summary.ball_coverage_pct != null ? `${summary.ball_coverage_pct.toFixed(1)}%` : "—"],
                    ["Detección directa", summary.ball_raw_detection_rate != null ? `${(summary.ball_raw_detection_rate * 100).toFixed(1)}%` : "—"],
                    ["Detector", `${summary.ball_detector_source ?? "—"}${summary.ball_detector_mode ? ` (${summary.ball_detector_mode})` : ""}`],
                    ["FP estáticos eliminados", String((summary.ball_static_fp_dropped ?? 0) + (summary.ball_static_fp_dropped_post_sahi ?? 0))],
                    ["Tiempo total", summary.total_seconds != null ? `${Math.round(summary.total_seconds / 60)} min` : "—"],
                    ["FPS procesados", summary.fps_processed != null ? summary.fps_processed.toFixed(1) : "—"],
                    ["Identidades", `${summary.consolidated_identities ?? "—"} (${summary.identities_with_dorsal ?? 0} c/dorsal)`],
                    ["Flags de revisión", String(summary.ball_review_flags ?? 0)],
                  ].map(([label, value]) => (
                    <div key={label} className="bg-slate-800/60 rounded-lg px-3 py-2">
                      <div className="text-slate-400">{label}</div>
                      <div className="text-white font-semibold mt-0.5">{value}</div>
                    </div>
                  ))}
                </div>

                {summary.ball_source_counts && Object.keys(summary.ball_source_counts).length > 0 && (
                  <div>
                    <p className="text-xs text-slate-400 mb-1">Fuente de cada detección de balón</p>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(summary.ball_source_counts).sort((a, b) => b[1] - a[1]).map(([src, n]) => (
                        <span key={src} className="text-xs px-2 py-1 rounded-md bg-slate-800 text-slate-300 border border-slate-700">
                          {src}: <span className="text-white font-semibold">{n}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {summary.stage_timings && Object.keys(summary.stage_timings).length > 0 && (
                  <div>
                    <p className="text-xs text-slate-400 mb-1">Tiempo por etapa (s)</p>
                    <div className="space-y-1">
                      {(() => {
                        const entries = Object.entries(summary.stage_timings!);
                        const maxT = Math.max(...entries.map(([, s]) => s), 1);
                        return entries.map(([stage, secs]) => (
                          <div key={stage} className="flex items-center gap-2 text-xs">
                            <span className="w-40 shrink-0 text-slate-400 truncate">{stage}</span>
                            <div className="flex-1 bg-slate-800 rounded h-3 overflow-hidden">
                              <div className="bg-blue-600 h-full" style={{ width: `${(secs / maxT) * 100}%` }} />
                            </div>
                            <span className="w-12 text-right text-slate-300">{secs.toFixed(0)}s</span>
                          </div>
                        ));
                      })()}
                    </div>
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

        {/* Analyze options modal */}
        {showAnalyzeModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div className="bg-slate-800 border border-slate-700 rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl space-y-5">
              <div className="flex items-center gap-2">
                <Settings2 size={18} className="text-blue-400" />
                <h3 className="font-semibold text-white text-base">Opciones de análisis</h3>
              </div>

              {/* Team names — labels the game + links rosters for player mapping */}
              <div className="space-y-2">
                <p className="text-sm font-medium text-white">Nombres de equipos</p>
                <p className="text-xs text-slate-400">
                  Se usan como etiqueta del partido y para vincular los rosters (mapeo dorsal→jugador).
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs text-slate-400 block mb-1">Local</label>
                    <input
                      type="text"
                      value={teamName1}
                      onChange={e => setTeamName1(e.target.value)}
                      placeholder="ej: Leones"
                      className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm placeholder-slate-500 focus:outline-none focus:border-blue-500"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400 block mb-1">Visitante</label>
                    <input
                      type="text"
                      value={teamName2}
                      onChange={e => setTeamName2(e.target.value)}
                      placeholder="ej: Águilas"
                      className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm placeholder-slate-500 focus:outline-none focus:border-blue-500"
                    />
                  </div>
                </div>
              </div>

              {/* Jersey descriptions — critical for FashionCLIP team classification */}
              <div className="space-y-2">
                <p className="text-sm font-medium text-white">Camisetas de equipos</p>
                <p className="text-xs text-slate-400">
                  Describe el color/estilo de cada camiseta para que FashionCLIP clasifique correctamente los equipos.
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs text-slate-400 block mb-1">Equipo 1 (local)</label>
                    <input
                      type="text"
                      value={jerseyTeam1}
                      onChange={e => setJerseyTeam1(e.target.value)}
                      placeholder="ej: white shirt"
                      className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm placeholder-slate-500 focus:outline-none focus:border-blue-500"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400 block mb-1">Equipo 2 (visitante)</label>
                    <input
                      type="text"
                      value={jerseyTeam2}
                      onChange={e => setJerseyTeam2(e.target.value)}
                      placeholder="ej: dark blue shirt"
                      className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm placeholder-slate-500 focus:outline-none focus:border-blue-500"
                    />
                  </div>
                </div>
              </div>

              {/* Game window — exclude warm-up / pre-game from metrics */}
              <div className="space-y-2">
                <p className="text-sm font-medium text-white">Ventana del juego (opcional)</p>
                <p className="text-xs text-slate-400">
                  Las métricas (posesión, pases, control, tiros) cuentan solo dentro de esta ventana.
                  Útil para excluir el calentamiento previo. Déjalo vacío para todo el video.
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs text-slate-400 block mb-1">Inicio (segundos)</label>
                    <input
                      type="number" min={0} step={1}
                      value={gameStartS}
                      onChange={e => setGameStartS(e.target.value)}
                      placeholder="ej: 55"
                      className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm placeholder-slate-500 focus:outline-none focus:border-blue-500"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400 block mb-1">Fin (segundos, vacío=fin)</label>
                    <input
                      type="number" min={0} step={1}
                      value={gameEndS}
                      onChange={e => setGameEndS(e.target.value)}
                      placeholder="ej: 380"
                      className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm placeholder-slate-500 focus:outline-none focus:border-blue-500"
                    />
                  </div>
                </div>
              </div>

              {/* Ball tracking quality (SAM 2.1 checkpoint) */}
              <div className="space-y-2">
                <p className="text-sm font-medium text-white">Calidad de tracking de balón (SAM 2.1)</p>
                <p className="text-xs text-slate-400">
                  Checkpoint mayor = mejor seguimiento del balón, pero más VRAM y tiempo.
                </p>
                <div className="flex items-center gap-1 bg-slate-800 rounded-lg p-1 w-fit flex-wrap">
                  {([
                    ["small", "Rápido"],
                    ["base_plus", "Equilibrado"],
                    ["large", "Máxima"],
                    ["efficienttam", "ETAM piloto"],
                  ] as const).map(([q, label]) => (
                    <button key={q} onClick={() => setBallQuality(q)}
                      className={clsx(
                        "px-3 py-1.5 text-xs rounded-md transition-colors",
                        ballQuality === q ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white",
                      )}>
                      {label} <span className="opacity-60">({q})</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Ball detector mode (TrackNet vs YOLO finetune) */}
              <div className="space-y-2">
                <p className="text-sm font-medium text-white">Detector de balón</p>
                <p className="text-xs text-slate-400">
                  Auto sigue el modelo activo global (Modelos → tracknet_ball). Forzar TrackNet o el
                  finetune YOLO para probar con este video.
                </p>
                <div className="flex items-center gap-1 bg-slate-800 rounded-lg p-1 w-fit flex-wrap">
                  {([
                    ["auto", "Auto (global)"],
                    ["tracknet", "TrackNet"],
                    ["yolo", "YOLO finetune"],
                  ] as const).map(([m, label]) => (
                    <button key={m} onClick={() => setBallMode(m)}
                      className={clsx(
                        "px-3 py-1.5 text-xs rounded-md transition-colors",
                        ballMode === m ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white",
                      )}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Pose skeleton toggle */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-white">Poses de jugadores</p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Proyecta el esqueleto COCO-17 en el video de salida (añade ~6 min al análisis)
                    </p>
                  </div>
                  <button
                    onClick={() => handleTogglePoses(!showPoses)}
                    disabled={updatingPoses}
                    className={clsx(
                      "relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-60",
                      showPoses ? "bg-blue-600" : "bg-slate-600"
                    )}
                    title={showPoses ? "Desactivar poses" : "Activar poses"}
                  >
                    <span
                      className={clsx(
                        "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
                        showPoses ? "translate-x-6" : "translate-x-1"
                      )}
                    />
                  </button>
                </div>
                {updatingPoses && (
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <Loader2 size={10} className="animate-spin" /> Guardando…
                  </p>
                )}
              </div>

              {/* Player filter input — only shown when poses are enabled */}
              {showPoses && (
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-white block">
                    Filtrar poses por jugador <span className="text-slate-400 font-normal">(opcional)</span>
                  </label>
                  <input
                    type="text"
                    value={poseFilterInput}
                    onChange={e => setPoseFilterInput(e.target.value)}
                    placeholder="Ej: 107, 182, 139"
                    className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white text-sm placeholder-slate-500 focus:outline-none focus:border-blue-500"
                  />
                  <p className="text-xs text-slate-400">
                    IDs separados por coma. Déjalo vacío para mostrar poses de todos los jugadores.
                    Los IDs de jugadores se muestran sobre cada jugador en el video anterior.
                  </p>
                  {poseFilterInput.trim() && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {poseFilterInput.split(",").map(s => s.trim()).filter(Boolean).map((id, i) => (
                        <span key={i} className="px-2 py-0.5 rounded-full bg-blue-500/20 border border-blue-500/30 text-blue-300 text-xs font-mono">
                          #{id}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {!showPoses && (
                <div className="flex items-center gap-2 text-xs text-slate-400 bg-slate-700/50 rounded-lg px-3 py-2">
                  <EyeOff size={12} />
                  El video de salida no incluirá esqueletos de poses.
                </div>
              )}

              <div className="flex gap-3 justify-end pt-1">
                <button
                  onClick={() => setShowAnalyzeModal(false)}
                  className="px-4 py-2 text-sm rounded-lg bg-slate-700 hover:bg-slate-600 text-white transition-colors"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleAnalyze}
                  className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium transition-colors"
                >
                  <Activity size={14} />
                  Iniciar análisis
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

        {/* Field-goal shooting (attempts / makes / FG%, with team split) */}
        {metrics && shotsAttempted > 0 && (
          <div className="bg-slate-800 rounded-xl p-5">
            <h2 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
              <Target size={16} className="text-orange-400" /> Tiros de campo
            </h2>
            <div className="grid grid-cols-3 gap-4 mb-4">
              {[
                { label: "Anotados", value: shotsMade },
                { label: "Intentos", value: shotsAttempted },
                { label: "FG%", value: `${fgPct(shotsMade, shotsAttempted)}%` },
              ].map(({ label, value }) => (
                <div key={label} className="text-center">
                  <p className="text-3xl font-bold text-orange-400">{value}</p>
                  <p className="text-xs text-slate-400 mt-1">{label}</p>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-lg bg-slate-700/40 px-3 py-2" style={{ borderLeft: `3px solid ${TEAM_COLORS[0]}` }}>
                <p className="text-slate-300 font-medium truncate">{chartTeam1}</p>
                <p className="text-slate-400">{t1Made}/{t1Att} · <span className="text-white">{fgPct(t1Made, t1Att)}% FG</span></p>
              </div>
              <div className="rounded-lg bg-slate-700/40 px-3 py-2" style={{ borderLeft: `3px solid ${TEAM_COLORS[1]}` }}>
                <p className="text-slate-300 font-medium truncate">{chartTeam2}</p>
                <p className="text-slate-400">{t2Made}/{t2Att} · <span className="text-white">{fgPct(t2Made, t2Att)}% FG</span></p>
              </div>
            </div>
            <p className="text-xs text-slate-500 mt-3">
              Intentos detectados por el aro; aciertos reforzados por el tablero anotado. Atribuidos al
              tirador (posesión previa) y a su equipo.
            </p>
          </div>
        )}

        {/* Hoops detected / configured */}
        {metrics && (() => {
          const tf = metrics.total_frames || 0;
          const hf = metrics.hoop_detected_frames ?? 0;
          const cov = tf > 0 ? Math.round((100 * hf) / tf) : 0;
          const cfg = metrics.hoops_configured ?? 0;
          const bb = metrics.hoops_with_backboard ?? 0;
          if (hf === 0 && cfg === 0) return null;
          return (
            <div className="bg-slate-800 rounded-xl p-5">
              <h2 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
                <Crosshair size={16} className="text-emerald-400" /> Aros
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                <div className="text-center">
                  <p className="text-3xl font-bold text-emerald-400">{cov}%</p>
                  <p className="text-xs text-slate-400 mt-1">Detección automática</p>
                </div>
                <div className="text-center">
                  <p className="text-3xl font-bold text-emerald-400">{hf.toLocaleString()}</p>
                  <p className="text-xs text-slate-400 mt-1">Frames auto-detectados</p>
                </div>
                <div className="text-center">
                  <p className="text-3xl font-bold text-emerald-400">{cfg}</p>
                  <p className="text-xs text-slate-400 mt-1">Canastas anotadas{bb > 0 ? ` (${bb} c/ tablero)` : ""}</p>
                </div>
              </div>
              {Array.isArray(metrics.hoops) && metrics.hoops.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {metrics.hoops.map((h) => (
                    <span key={h.hoop_id} className="text-xs px-3 py-1.5 rounded-lg bg-slate-700/60 text-slate-200 border border-slate-600">
                      Aro #{h.hoop_id} · <span className="text-white font-semibold">{h.team_name || (h.team_id === 1 ? "Local" : "Visitante")}</span>
                      {h.has_backboard ? " · c/ tablero" : ""}
                    </span>
                  ))}
                </div>
              )}
              <p className="text-xs text-slate-500 mt-3">
                El % es la <strong>detección automática</strong> del aro (suele ser baja).{cfg > 0
                  ? " Tienes canastas anotadas a mano: se propagan a todo el video y son las que usan el conteo de tiros (no dependen de este %)."
                  : " Anota el aro para fijar la canasta en todo el video y mejorar el conteo de tiros (no depende de este %)."}
              </p>
            </div>
          );
        })()}

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
                { label: `Posesión ${chartTeam1}`, value: `${metrics.team1_possession_pct}%` },
                { label: `Posesión ${chartTeam2}`, value: `${metrics.team2_possession_pct}%` },
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
                    <Bar dataKey="team1" name={chartTeam1} fill={TEAM_COLORS[0]} />
                    <Bar dataKey="team2" name={chartTeam2} fill={TEAM_COLORS[1]} />
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
                <p className="text-sm">No hay eventos CV. Analiza el video para ver pases, robos y más.</p>
              </div>
            ) : (
              cvEvents.map((ev, i) => {
                const cfg = CV_EVENT_CONFIG[ev.event_type];
                return (
                  <button key={i} onClick={() => annotatedVideoUrl && setEventPopup(ev)}
                    disabled={!annotatedVideoUrl}
                    title={annotatedVideoUrl ? "Ver el momento del evento" : "Video anotado no disponible"}
                    className="w-full text-left flex items-center gap-3 bg-slate-800 hover:bg-slate-700/70 rounded-lg px-4 py-3 transition-colors disabled:cursor-default">
                    <span className={clsx("flex items-center justify-center w-7 h-7 rounded-full border text-xs", cfg?.bg ?? "bg-slate-700 border-slate-600", cfg?.color ?? "text-slate-400")}>
                      {cfg?.icon ?? <Activity size={14} />}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-white font-medium text-sm">
                        {cfg?.label ?? ev.event_type.replace("_", " ")}
                        {ev.edited && <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300">editado</span>}
                      </div>
                      {ev.description && <div className="text-xs text-slate-400 truncate">{ev.description}</div>}
                    </div>
                    {ev.player_track_id != null && (
                      <span className="text-xs text-slate-500">
                        {metrics?.players.find(p => p.track_id === ev.player_track_id)?.display_label ?? `#${ev.player_track_id}`}
                      </span>
                    )}
                    {ev.team_id != null && (
                      <span className="text-xs px-1.5 py-0.5 rounded" style={{ backgroundColor: TEAM_COLORS[ev.team_id] + "33", color: TEAM_COLORS[ev.team_id] }}>
                        Equipo {ev.team_id + 1}
                      </span>
                    )}
                    <span className="text-xs text-slate-500 ml-auto shrink-0">
                      {ev.time_s != null ? `${ev.time_s.toFixed(1)}s` : `f${ev.frame}`}
                    </span>
                  </button>
                );
              })
            )}
          </div>
        )}

        {/* Tab: Players */}
        {activeTab === "players" && metrics && (() => {
          const identifiedCount = metrics.players.filter(p => p.jersey_number).length;
          const rows = [...metrics.players]
            .filter(p => !onlyIdentified || p.jersey_number)
            .sort((a, b) => (b.minutes_played ?? 0) - (a.minutes_played ?? 0));
          return (
          <div className="space-y-3">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <p className="text-xs text-slate-400">
                {metrics.players.length} identidades · <span className="text-emerald-400 font-medium">{identifiedCount} con dorsal</span>.
                Ordenado por minutos (los jugadores reales arriba; los fragmentos sin dorsal, abajo).
              </p>
              <div className="flex items-center gap-2">
                <Link
                  href={`/games/${id}/roster-mapping`}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium border border-emerald-600/50 text-emerald-300 hover:bg-emerald-600/10 transition-colors"
                >
                  Asignar jugadores →
                </Link>
                <button
                  onClick={() => setOnlyIdentified(v => !v)}
                  className={clsx(
                    "px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors",
                    onlyIdentified ? "bg-emerald-600 border-emerald-500 text-white"
                      : "border-slate-600 text-slate-300 hover:border-slate-400",
                  )}
                >
                  {onlyIdentified ? "Mostrando solo con dorsal" : "Solo identificados (con dorsal)"}
                </button>
              </div>
            </div>
            <div className="bg-slate-800 rounded-xl overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-left text-xs text-slate-400">
                  {["Jugador", "Equipo", "Min.", "Distancia (m)", "Vel. prom.", "Vel. máx.", "Posesión", "Pases", "Intercep.", "Tiros (FG)"].map(h => (
                    <th key={h} className="px-4 py-3 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {rows.map(p => {
                  const maxSpd = p.max_speed_kmh;
                  const spdColor = maxSpd > 25 ? "text-red-400" : maxSpd > 15 ? "text-amber-400" : "text-green-400";
                  const avgSpd = p.avg_speed_kmh;
                  const avgColor = avgSpd > 20 ? "text-red-400" : avgSpd > 10 ? "text-amber-400" : "text-green-400";
                  const label = p.display_label ?? (p.jersey_number ? `#${p.jersey_number}` : `#${p.track_id}`);
                  return (
                    <tr key={p.track_id} className="hover:bg-slate-700/50 transition-colors">
                      <td className="px-4 py-3 font-mono font-semibold text-white">
                        {p.player_id ? (
                          <Link href={`/players/${p.player_id}`} className="text-blue-400 hover:underline">{label}</Link>
                        ) : label}
                        {p.jersey_number && (
                          <span className="ml-2 text-[10px] uppercase tracking-wide text-slate-500">dorsal</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-block rounded-full px-2 py-0.5 text-xs font-semibold text-white"
                          style={{ backgroundColor: TEAM_COLORS[(p.team_id ?? 1) - 1] ?? "#6b7280" }}>
                          {p.team_id === 1 ? (metrics.home_team_name ?? "Local")
                            : p.team_id === 2 ? (metrics.away_team_name ?? "Visitante")
                            : "?"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-200">{(p.minutes_played ?? 0).toFixed(1)}</td>
                      <td className="px-4 py-3 text-slate-200">{p.total_distance_m.toFixed(1)}</td>
                      <td className={`px-4 py-3 font-medium ${avgColor}`}>{avgSpd.toFixed(1)} km/h</td>
                      <td className={`px-4 py-3 font-medium ${spdColor}`}>{maxSpd.toFixed(1)} km/h</td>
                      <td className="px-4 py-3 text-slate-200">{p.possession_frames}</td>
                      <td className="px-4 py-3 text-slate-200">{p.passes_made}</td>
                      <td className="px-4 py-3 text-slate-200">{p.interceptions_made}</td>
                      <td className="px-4 py-3 text-slate-200">
                        {(p.shots_attempted ?? 0) > 0
                          ? `${p.shots_made ?? 0}/${p.shots_attempted} (${fgPct(p.shots_made ?? 0, p.shots_attempted ?? 0)}%)`
                          : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
          </div>
          );
        })()}
      </div>

      {eventPopup && annotatedVideoUrl && (
        <EventClipModal
          event={eventPopup}
          videoUrl={annotatedVideoUrl}
          pad={clipPad}
          setPad={setClipPad}
          players={(metrics?.players ?? []).map(p => ({ track_id: p.track_id, label: p.display_label ?? (p.jersey_number ? `#${p.jersey_number}` : `#${p.track_id}`) }))}
          onClose={() => setEventPopup(null)}
          onSaved={(updated) => {
            setCvEvents(prev => prev.map(e => e.idx === updated.idx ? { ...e, ...updated } : e));
            setEventPopup(null);
          }}
          gameId={id}
        />
      )}
    </AppShell>
  );
}

function EventClipModal({ event, videoUrl, pad, setPad, players, onClose, onSaved, gameId }: {
  event: CvEvent; videoUrl: string; pad: number; setPad: (n: number) => void;
  players: { track_id: number; label: string }[];
  onClose: () => void; onSaved: (e: CvEvent) => void; gameId: string;
}) {
  const vRef = useRef<HTMLVideoElement>(null);
  const [evType, setEvType] = useState(event.event_type);
  const [trackId, setTrackId] = useState<number | undefined>(event.player_track_id);
  const [saving, setSaving] = useState(false);
  const t = event.time_s ?? 0;
  const start = Math.max(0, t - pad);
  const end = t + pad;

  useEffect(() => {
    const v = vRef.current;
    if (!v) return;
    const seek = () => { v.currentTime = start; v.play().catch(() => {}); };
    const onTime = () => { if (v.currentTime >= end || v.currentTime < start - 0.5) v.currentTime = start; };
    v.addEventListener("loadedmetadata", seek);
    v.addEventListener("timeupdate", onTime);
    if (v.readyState >= 1) seek();
    return () => { v.removeEventListener("loadedmetadata", seek); v.removeEventListener("timeupdate", onTime); };
  }, [start, end]);

  async function save() {
    setSaving(true);
    try {
      const payload: { new_type?: string; new_player_track_id?: number } = {};
      if (evType !== event.event_type) payload.new_type = evType;
      if (trackId != null && trackId !== event.player_track_id) payload.new_player_track_id = trackId;
      if (Object.keys(payload).length === 0) { onClose(); return; }
      const updated = await correctCvEvent(gameId, event.idx ?? 0, payload);
      onSaved(updated);
    } catch { /* ignore */ } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="bg-slate-800 border border-slate-700 rounded-2xl max-w-2xl w-full shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-700">
          <h3 className="font-semibold text-white text-sm">Momento del evento · {t.toFixed(1)}s</h3>
          <button onClick={onClose}><X size={18} className="text-slate-400 hover:text-white" /></button>
        </div>
        <div className="p-5 space-y-4">
          <video ref={vRef} src={videoUrl} controls autoPlay muted loop className="w-full rounded-lg bg-black" />
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span>Ventana:</span>
            {[1, 2, 3, 5].map(n => (
              <button key={n} onClick={() => setPad(n)}
                className={clsx("px-2 py-1 rounded", pad === n ? "bg-blue-600 text-white" : "bg-slate-700 text-slate-300")}>
                ±{n}s
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400">Tipo de evento</label>
              <select value={evType} onChange={e => setEvType(e.target.value)}
                className="w-full mt-1 bg-slate-700 text-white text-sm rounded-lg px-3 py-2">
                {CV_EVENT_TYPES.includes(evType) ? null : <option value={evType}>{evType}</option>}
                {CV_EVENT_TYPES.map(tp => <option key={tp} value={tp}>{tp.replace("_", " ")}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-400">Jugador</label>
              <select value={trackId ?? ""} onChange={e => setTrackId(e.target.value ? Number(e.target.value) : undefined)}
                className="w-full mt-1 bg-slate-700 text-white text-sm rounded-lg px-3 py-2">
                <option value="">— sin asignar —</option>
                {players.map(p => <option key={p.track_id} value={p.track_id}>{p.label}</option>)}
              </select>
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="px-3 py-2 text-sm text-slate-300 hover:text-white">Cancelar</button>
            <button onClick={save} disabled={saving}
              className="px-4 py-2 text-sm rounded-lg bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50">
              {saving ? "Guardando…" : "Guardar corrección"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
