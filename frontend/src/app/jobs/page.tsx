"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { listJobs } from "@/lib/api";
import { clsx } from "clsx";
import {
  RefreshCw,
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  ArrowRight,
  Activity,
} from "lucide-react";

interface Job {
  id: string;
  game_id: string;
  status: string;
  current_stage: string;
  progress_pct: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

const STATUS_CONFIG: Record<string, { icon: React.ReactNode; badge: string; label: string }> = {
  pending: { icon: <Clock size={14} className="text-slate-400" />, badge: "badge-gray", label: "Pending" },
  running: { icon: <Loader2 size={14} className="text-primary-500 animate-spin" />, badge: "badge-blue", label: "Running" },
  done: { icon: <CheckCircle2 size={14} className="text-success-500" />, badge: "badge-green", label: "Done" },
  failed: { icon: <XCircle size={14} className="text-danger-500" />, badge: "badge-red", label: "Failed" },
};

function elapsed(started: string | null, finished: string | null): string {
  if (!started) return "—";
  const s = new Date(started);
  const e = finished ? new Date(finished) : new Date();
  const secs = Math.round((e.getTime() - s.getTime()) / 1000);
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

export default function JobsPage() {
  const router = useRouter();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (showRefreshing = false) => {
    if (showRefreshing) setRefreshing(true);
    try {
      const data = await listJobs(0, 50);
      const items = Array.isArray(data) ? data : data.items ?? [];
      setJobs(items);
    } catch {
      router.replace("/login");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [router]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = setInterval(() => load(), 5000);
    return () => clearInterval(timer);
  }, [autoRefresh, load]);

  const hasRunning = jobs.some((j) => j.status === "running" || j.status === "pending");
  const doneCount = jobs.filter((j) => j.status === "done").length;
  const failedCount = jobs.filter((j) => j.status === "failed").length;
  const runningCount = jobs.filter((j) => j.status === "running" || j.status === "pending").length;

  return (
    <AppShell
      title="Analysis Jobs"
      subtitle={`${jobs.length} recent jobs`}
      actions={
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer select-none">
            <div
              onClick={() => setAutoRefresh((v) => !v)}
              className={clsx(
                "h-5 w-9 rounded-full transition-colors cursor-pointer relative",
                autoRefresh ? "bg-primary-500" : "bg-slate-200"
              )}
            >
              <div className={clsx("absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform", autoRefresh ? "translate-x-4" : "translate-x-0.5")} />
            </div>
            <span>Auto-refresh</span>
            {hasRunning && <span className="h-1.5 w-1.5 rounded-full bg-primary-500 animate-pulse" />}
          </label>
          <button className="btn-secondary btn-sm" onClick={() => load(true)} disabled={refreshing}>
            <RefreshCw size={13} className={clsx(refreshing && "animate-spin")} />
            Refresh
          </button>
        </div>
      }
    >
      {/* Stats row */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { label: "Completed", value: doneCount, color: "text-success-600", bg: "bg-success-50" },
          { label: "In Progress", value: runningCount, color: "text-primary-600", bg: "bg-primary-50" },
          { label: "Failed", value: failedCount, color: "text-danger-600", bg: "bg-danger-50" },
        ].map((s) => (
          <div key={s.label} className={clsx("rounded-xl p-4 flex items-center gap-3", s.bg)}>
            <p className={clsx("text-2xl font-bold", s.color)}>{s.value}</p>
            <p className="text-sm text-slate-600">{s.label}</p>
          </div>
        ))}
      </div>

      {loading ? (
        <div className="card flex items-center justify-center py-20 text-slate-400">
          <Loader2 size={24} className="animate-spin" />
        </div>
      ) : jobs.length === 0 ? (
        <div className="card text-center py-20">
          <div className="mx-auto mb-4 h-14 w-14 rounded-2xl bg-slate-100 flex items-center justify-center">
            <Activity size={24} className="text-slate-400" />
          </div>
          <p className="font-display font-bold text-slate-800 mb-1">No jobs yet</p>
          <p className="text-sm text-slate-500">
            Upload a video in a game to start analysis.
          </p>
          <Link href="/games" className="btn-primary inline-flex mt-5 btn-sm">
            Go to Games
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => {
            const cfg = STATUS_CONFIG[job.status] ?? STATUS_CONFIG.pending;
            return (
              <div key={job.id} className="card p-4 flex flex-col sm:flex-row sm:items-center gap-4">
                {/* Status */}
                <div className="flex items-center gap-3 sm:w-36">
                  {cfg.icon}
                  <span className={clsx("badge capitalize", cfg.badge)}>{job.status}</span>
                </div>

                {/* Stage + progress */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800 capitalize mb-1.5">
                    {job.current_stage.replace(/_/g, " ")}
                  </p>
                  <div className="flex items-center gap-3">
                    <div className="progress-track flex-1 max-w-xs">
                      <div
                        className={clsx(
                          "progress-bar",
                          job.status === "done" ? "bg-success-500" :
                          job.status === "failed" ? "bg-danger-400" : ""
                        )}
                        style={{ width: `${job.progress_pct}%` }}
                      />
                    </div>
                    <span className="text-xs text-slate-500 font-medium">{job.progress_pct}%</span>
                  </div>
                  {job.status === "failed" && job.error_message && (
                    <p className="mt-1 text-xs text-danger-600 truncate" title={job.error_message}>
                      {job.error_message.slice(0, 80)}
                    </p>
                  )}
                </div>

                {/* Meta */}
                <div className="text-xs text-slate-400 space-y-0.5 sm:text-right flex-shrink-0">
                  <p>
                    Game:{" "}
                    <Link href={`/games/${job.game_id}`} className="text-primary-600 hover:underline font-mono">
                      {job.game_id.slice(0, 8)}…
                    </Link>
                  </p>
                  <p>Duration: {elapsed(job.started_at, job.finished_at)}</p>
                  <p>{new Date(job.created_at).toLocaleString()}</p>
                </div>

                {/* Action */}
                {job.status === "done" && (
                  <Link href={`/games/${job.game_id}`} className="btn-ghost btn-sm flex-shrink-0">
                    Results
                    <ArrowRight size={14} />
                  </Link>
                )}
              </div>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
