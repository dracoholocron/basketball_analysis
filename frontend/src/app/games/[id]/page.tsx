"use client";
import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import Navbar from "@/components/Navbar";
import {
  getGame,
  uploadVideo,
  getGameMetrics,
  pollJobUntilDone,
} from "@/lib/api";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

interface PlayerMetric {
  track_id: number;
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

const TEAM_COLORS = ["#3b82f6", "#ef4444"];

export default function GameDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [game, setGame] = useState<Record<string, unknown> | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [jobStatus, setJobStatus] = useState<{
    status: string;
    progress_pct: number;
    current_stage: string;
    id?: string;
    output_s3_key?: string;
    error_message?: string | null;
  } | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!id) return;
    getGame(id).then(setGame);
    getGameMetrics(id).then(setMetrics).catch(() => null);
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
        setJobStatus((prev) => prev ? { ...prev, status: "failed", error_message: err.message } : prev);
      });
      const m = await getGameMetrics(id);
      setMetrics(m);
    } catch (err) {
      console.error(err);
    } finally {
      setUploading(false);
    }
  }

  const possessionData = metrics
    ? [
        { name: "Team 1", value: metrics.team1_possession_pct },
        { name: "Team 2", value: metrics.team2_possession_pct },
      ]
    : [];

  const passData = metrics
    ? [
        { name: "Passes", team1: metrics.team1_passes, team2: metrics.team2_passes },
        { name: "Interceptions", team1: metrics.team1_interceptions, team2: metrics.team2_interceptions },
      ]
    : [];

  return (
    <>
      <Navbar />
      <main className="mx-auto max-w-7xl px-4 py-8 space-y-6">
        {/* Header */}
        <div className="card">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold">
                {(game?.location as string) ?? "Game Detail"}
              </h1>
              <p className="text-sm text-gray-500 mt-1">
                {(game?.game_date as string) ?? ""} ·{" "}
                <span className="font-medium text-primary-600">{(game?.court_level as string) ?? ""}</span>
                {(game?.is_half_court as boolean) && (
                  <span className="ml-2 text-amber-600 font-medium">• Half-court</span>
                )}
              </p>
              <p className="text-xs font-mono text-gray-400 mt-1">{id}</p>
            </div>

            {/* Video Upload */}
            <div className="flex flex-col gap-2">
              <input ref={fileRef} type="file" accept="video/*" className="hidden" id="video-input" />
              <div className="flex gap-2">
                <label htmlFor="video-input" className="btn-secondary cursor-pointer">
                  Choose Video
                </label>
                <button
                  className="btn-primary"
                  onClick={handleUpload}
                  disabled={uploading}
                >
                  {uploading ? "Processing…" : "Analyze"}
                </button>
              </div>

              {jobStatus && (
                <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-medium capitalize">{jobStatus.status}</span>
                    <span className="text-gray-500">{jobStatus.progress_pct}%</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-gray-200 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-primary-500 transition-all duration-500"
                      style={{ width: `${jobStatus.progress_pct}%` }}
                    />
                  </div>
                  <p className="mt-1.5 text-xs text-gray-500 capitalize">
                    {jobStatus.current_stage.replace(/_/g, " ")}
                  </p>
                  {jobStatus.status === "done" && jobStatus.id && (
                    <a
                      href={`${process.env.NEXT_PUBLIC_API_URL}/api/v1/jobs/${jobStatus.id}/annotated-video`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2 inline-flex items-center gap-1 text-primary-600 hover:underline text-xs font-medium"
                    >
                      Download annotated video →
                    </a>
                  )}
                  {jobStatus.status === "failed" && jobStatus.error_message && (
                    <p className="mt-2 text-xs text-red-600 bg-red-50 rounded px-2 py-1 ring-1 ring-red-200">
                      Error: {jobStatus.error_message}
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {metrics ? (
          <>
            {/* KPI cards */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { label: "Total Frames", value: metrics.total_frames.toLocaleString() },
                { label: "Team 1 Possession", value: `${metrics.team1_possession_pct}%` },
                { label: "Team 2 Possession", value: `${metrics.team2_possession_pct}%` },
                { label: "Total Players Tracked", value: metrics.players.length },
              ].map((kpi) => (
                <div key={kpi.label} className="card text-center">
                  <p className="text-3xl font-bold text-primary-600">{kpi.value}</p>
                  <p className="text-sm text-gray-500 mt-1">{kpi.label}</p>
                </div>
              ))}
            </div>

            {/* Charts row */}
            <div className="grid gap-6 lg:grid-cols-2">
              {/* Possession pie */}
              <div className="card">
                <h2 className="text-lg font-semibold mb-4">Ball Possession</h2>
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={possessionData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={({ name, value }) => `${name}: ${value}%`}>
                      {possessionData.map((_, i) => (
                        <Cell key={i} fill={TEAM_COLORS[i % TEAM_COLORS.length]} />
                      ))}
                    </Pie>
                    <Legend />
                    <Tooltip formatter={(v) => `${v}%`} />
                  </PieChart>
                </ResponsiveContainer>
              </div>

              {/* Passes / Interceptions bar */}
              <div className="card">
                <h2 className="text-lg font-semibold mb-4">Passes & Interceptions</h2>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={passData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis allowDecimals={false} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="team1" name="Team 1" fill={TEAM_COLORS[0]} />
                    <Bar dataKey="team2" name="Team 2" fill={TEAM_COLORS[1]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Player table */}
            <div className="card overflow-x-auto">
              <h2 className="text-lg font-semibold mb-4">Player Metrics</h2>
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                    <th className="pb-2 pr-4">Track ID</th>
                    <th className="pb-2 pr-4">Team</th>
                    <th className="pb-2 pr-4">Distance (m)</th>
                    <th className="pb-2 pr-4">Max Speed (km/h)</th>
                    <th className="pb-2 pr-4">Possession (frames)</th>
                    <th className="pb-2 pr-4">Passes</th>
                    <th className="pb-2">Interceptions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {metrics.players
                    .sort((a, b) => b.total_distance_m - a.total_distance_m)
                    .map((p) => (
                      <tr key={p.track_id} className="hover:bg-gray-50 transition-colors">
                        <td className="py-2 pr-4 font-mono font-semibold">#{p.track_id}</td>
                        <td className="py-2 pr-4">
                          <span
                            className="inline-block rounded-full px-2 py-0.5 text-xs font-semibold text-white"
                            style={{ backgroundColor: TEAM_COLORS[(p.team_id ?? 1) - 1] ?? "#6b7280" }}
                          >
                            T{p.team_id ?? "?"}
                          </span>
                        </td>
                        <td className="py-2 pr-4">{p.total_distance_m.toFixed(1)}</td>
                        <td className="py-2 pr-4">{p.max_speed_kmh.toFixed(1)}</td>
                        <td className="py-2 pr-4">{p.possession_frames}</td>
                        <td className="py-2 pr-4">{p.passes_made}</td>
                        <td className="py-2">{p.interceptions_made}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <div className="card text-center py-16 text-gray-400">
            <p className="text-4xl mb-3">🎬</p>
            <p className="font-medium">No analysis yet.</p>
            <p className="text-sm mt-1">Upload a video and click Analyze to get started.</p>
          </div>
        )}
      </main>
    </>
  );
}
