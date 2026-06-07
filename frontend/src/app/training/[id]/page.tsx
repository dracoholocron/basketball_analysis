"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import AppShell from "@/components/layout/AppShell";
import {
  getTrainingSession,
  triggerTrainingAnalysis,
  getTrainingCvEvents,
  getTrainingHighlights,
} from "@/lib/api";
import {
  Activity, AlertCircle, CheckCircle2, Clock, Loader2,
  RefreshCw, Zap, Target, BarChart2, Film,
} from "lucide-react";
import { clsx } from "clsx";
import Link from "next/link";

interface ShootingMetric {
  frame: number;
  person_id: number;
  elbow_l?: number;
  elbow_r?: number;
  knee_l?: number;
  knee_r?: number;
  hip_l?: number;
  hip_r?: number;
  release_angle?: number;
}

interface CvEvent {
  type: string;
  frame: number;
  track_id?: number;
}

interface TrainingSession {
  id: string;
  sport_drill: string | null;
  status: string;
  video_s3_key: string | null;
  created_at: string;
  celery_task_id?: string;
  error_message?: string;
  metrics: ShootingMetric[];
}

const EVENT_COLORS: Record<string, string> = {
  shot_attempt: "bg-orange-500",
  rebound: "bg-blue-500",
  steal: "bg-purple-500",
  default: "bg-slate-500",
};

const EVENT_ICONS: Record<string, React.ReactNode> = {
  shot_attempt: <Target size={14} />,
  rebound: <Activity size={14} />,
  steal: <Zap size={14} />,
};

const STATUS_CONFIG: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  pending:   { color: "text-slate-400",  icon: <Clock size={14} />,                          label: "Pendiente" },
  uploaded:  { color: "text-blue-500",   icon: <Activity size={14} />,                       label: "Video subido" },
  analyzing: { color: "text-amber-500",  icon: <Loader2 size={14} className="animate-spin" />, label: "Analizando con RTMPose…" },
  done:      { color: "text-green-500",  icon: <CheckCircle2 size={14} />,                    label: "Completado" },
  failed:    { color: "text-red-500",    icon: <AlertCircle size={14} />,                     label: "Error" },
};

function avg(arr: (number | undefined)[]) {
  const vals = arr.filter((v): v is number => v !== undefined && v !== null);
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
}

export default function TrainingDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [session, setSession] = useState<TrainingSession | null>(null);
  const [cvEvents, setCvEvents] = useState<CvEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [reanalyzing, setReanalyzing] = useState(false);
  const [activeTab, setActiveTab] = useState<"metrics" | "events" | "highlights">("metrics");

  const fetchAll = async () => {
    try {
      const [sess, events] = await Promise.all([
        getTrainingSession(id),
        getTrainingCvEvents(id).catch(() => []),
      ]);
      setSession(sess);
      setCvEvents(events);
    } catch {
      router.replace("/login");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
    // Poll while analyzing
    const interval = setInterval(() => {
      if (session?.status === "analyzing") fetchAll();
    }, 5000);
    return () => clearInterval(interval);
  }, [id, session?.status]);

  const handleReanalyze = async () => {
    if (!session) return;
    setReanalyzing(true);
    try {
      await triggerTrainingAnalysis(id);
      await fetchAll();
    } finally {
      setReanalyzing(false);
    }
  };

  if (loading) {
    return (
      <AppShell>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="animate-spin text-blue-500" size={32} />
        </div>
      </AppShell>
    );
  }

  if (!session) return null;

  const statusCfg = STATUS_CONFIG[session.status] ?? STATUS_CONFIG.pending;
  const metrics = session.metrics ?? [];
  const avgElbowR  = avg(metrics.map(m => m.elbow_r));
  const avgKneeR   = avg(metrics.map(m => m.knee_r));
  const avgRelease = avg(metrics.map(m => m.release_angle));
  const hasKps     = metrics.length > 0;

  const shotEvents    = cvEvents.filter(e => e.type === "shot_attempt");
  const reboundEvents = cvEvents.filter(e => e.type === "rebound");
  const stealEvents   = cvEvents.filter(e => e.type === "steal");

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <Link href="/training" className="text-sm text-slate-400 hover:text-white mb-2 block">
              ← Sesiones
            </Link>
            <h1 className="text-2xl font-bold text-white">
              {session.sport_drill ?? "Sesión de entrenamiento"}
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              {new Date(session.created_at).toLocaleDateString("es-MX", {
                weekday: "long", year: "numeric", month: "long", day: "numeric",
              })}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className={clsx("flex items-center gap-1.5 text-sm font-medium", statusCfg.color)}>
              {statusCfg.icon}
              {statusCfg.label}
            </span>
            {session.video_s3_key && session.status !== "analyzing" && (
              <button
                onClick={handleReanalyze}
                disabled={reanalyzing}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
              >
                {reanalyzing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                Re-analizar
              </button>
            )}
          </div>
        </div>

        {/* Error message */}
        {session.status === "failed" && session.error_message && (
          <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 text-sm">
            {session.error_message}
          </div>
        )}

        {/* Stat cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: "Tiros detectados", value: shotEvents.length, icon: <Target size={16} className="text-orange-400" /> },
            { label: "Rebotes",          value: reboundEvents.length, icon: <Activity size={16} className="text-blue-400" /> },
            { label: "Robos",            value: stealEvents.length, icon: <Zap size={16} className="text-purple-400" /> },
            { label: "Frames analizados",value: metrics.length, icon: <BarChart2 size={16} className="text-green-400" /> },
          ].map(({ label, value, icon }) => (
            <div key={label} className="bg-slate-800 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-1">{icon}<span className="text-xs text-slate-400">{label}</span></div>
              <p className="text-2xl font-bold text-white">{value}</p>
            </div>
          ))}
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-slate-800 p-1 rounded-lg w-fit">
          {(["metrics", "events", "highlights"] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={clsx(
                "px-4 py-1.5 text-sm rounded-md capitalize transition-colors",
                activeTab === tab
                  ? "bg-blue-600 text-white"
                  : "text-slate-400 hover:text-white",
              )}
            >
              {tab === "metrics" ? "Métricas de pose" : tab === "events" ? "Eventos" : "Highlights"}
            </button>
          ))}
        </div>

        {/* Tab: Metrics */}
        {activeTab === "metrics" && (
          <div className="space-y-4">
            {!hasKps && session.status === "done" && (
              <p className="text-slate-400 text-sm">No hay datos de pose disponibles para esta sesión.</p>
            )}
            {!hasKps && session.status !== "done" && (
              <p className="text-slate-400 text-sm">
                {session.status === "analyzing"
                  ? "Analizando… los datos aparecerán cuando el proceso termine."
                  : "Sube un video y ejecuta el análisis para ver las métricas de pose."}
              </p>
            )}
            {hasKps && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {[
                  { label: "Ángulo de codo (der.)", value: avgElbowR, unit: "°" },
                  { label: "Ángulo de rodilla (der.)", value: avgKneeR, unit: "°" },
                  { label: "Ángulo de lanzamiento", value: avgRelease, unit: "°" },
                ].map(({ label, value, unit }) => (
                  <div key={label} className="bg-slate-800 rounded-xl p-5">
                    <p className="text-xs text-slate-400 mb-1">{label}</p>
                    <p className="text-3xl font-bold text-white">
                      {value !== null ? `${value.toFixed(1)}${unit}` : "—"}
                    </p>
                    {hasKps && (
                      <span className="text-xs text-green-400 mt-1 block">RTMPose real data</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab: Events */}
        {activeTab === "events" && (
          <div className="space-y-2">
            {cvEvents.length === 0 ? (
              <p className="text-slate-400 text-sm">No se detectaron eventos en esta sesión.</p>
            ) : (
              cvEvents.map((ev, i) => (
                <div key={i} className="flex items-center gap-3 bg-slate-800 rounded-lg px-4 py-3">
                  <span className={clsx(
                    "flex items-center justify-center w-7 h-7 rounded-full text-white text-xs",
                    EVENT_COLORS[ev.type] ?? EVENT_COLORS.default,
                  )}>
                    {EVENT_ICONS[ev.type] ?? <Activity size={14} />}
                  </span>
                  <span className="text-white capitalize">{ev.type.replace("_", " ")}</span>
                  <span className="text-slate-400 text-sm ml-auto">Frame {ev.frame}</span>
                  {ev.track_id != null && (
                    <span className="text-slate-500 text-xs">jugador #{ev.track_id}</span>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {/* Tab: Highlights */}
        {activeTab === "highlights" && (
          <div className="flex flex-col items-center justify-center py-16 gap-4 text-slate-400">
            <Film size={48} className="opacity-30" />
            <p className="text-sm">Los highlights se generan automáticamente tras el análisis.</p>
            {session.status === "done" && cvEvents.length > 0 && (
              <button
                onClick={handleReanalyze}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm"
              >
                Generar highlights
              </button>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
