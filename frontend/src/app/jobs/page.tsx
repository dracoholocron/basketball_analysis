"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Navbar from "@/components/Navbar";
import { listJobs } from "@/lib/api";
import { clsx } from "clsx";

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

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-700",
  running: "bg-blue-100 text-blue-700",
  done: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
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

  const load = useCallback(() => {
    listJobs(0, 50)
      .then((data: Job[] | { items: Job[] }) => {
        const items = Array.isArray(data) ? data : data.items;
        setJobs(items);
      })
      .catch(() => router.replace("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [autoRefresh, load]);

  const hasRunning = jobs.some((j) => j.status === "running" || j.status === "pending");

  return (
    <>
      <Navbar />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Jobs</h1>
            <p className="text-sm text-gray-500 mt-0.5">{jobs.length} recent</p>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-primary-600"
              />
              Auto-refresh {hasRunning && <span className="inline-block h-2 w-2 rounded-full bg-blue-500 animate-pulse" />}
            </label>
            <button className="btn-secondary text-sm" onClick={load}>Refresh</button>
          </div>
        </div>

        {loading ? (
          <div className="text-center py-20 text-gray-400">Loading…</div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-20 text-gray-400">
            No jobs yet. Upload a video in a game to start analysis.
          </div>
        ) : (
          <div className="card overflow-x-auto p-0">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs text-gray-500">
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Stage</th>
                  <th className="px-4 py-3">Progress</th>
                  <th className="px-4 py-3">Game</th>
                  <th className="px-4 py-3">Duration</th>
                  <th className="px-4 py-3">Created</th>
                  <th className="px-4 py-3">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {jobs.map((job) => (
                  <tr key={job.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <span className={clsx("inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize", STATUS_COLORS[job.status] ?? "bg-gray-100 text-gray-700")}>
                        {job.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-600 capitalize">
                      {job.current_stage.replace(/_/g, " ")}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-24 rounded-full bg-gray-200 overflow-hidden">
                          <div
                            className={clsx("h-full rounded-full transition-all", job.status === "done" ? "bg-green-500" : job.status === "failed" ? "bg-red-400" : "bg-primary-500")}
                            style={{ width: `${job.progress_pct}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-500">{job.progress_pct}%</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Link href={`/games/${job.game_id}`} className="font-mono text-xs text-primary-600 hover:underline">
                        {job.game_id.slice(0, 8)}…
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">
                      {elapsed(job.started_at, job.finished_at)}
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs">
                      {new Date(job.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">
                      {job.status === "failed" && job.error_message ? (
                        <span className="text-xs text-red-600 max-w-xs truncate block" title={job.error_message}>
                          {job.error_message.slice(0, 60)}{job.error_message.length > 60 ? "…" : ""}
                        </span>
                      ) : job.status === "done" ? (
                        <Link href={`/games/${job.game_id}`} className="text-xs text-primary-600 hover:underline">
                          View results →
                        </Link>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </>
  );
}
