"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { getEventHeatmap, getMatchup, getLiveKeysStatus } from "@/lib/api";
import { ArrowLeft, Loader2, TrendingUp, TrendingDown } from "lucide-react";
import { clsx } from "clsx";

interface MetricTarget {
  scope: "us" | "them" | "player";
  player_name?: string;
  metric: string;
  target: number;
  current: number;
}

interface LiveKey {
  key_id: string;
  title: string;
  live_status: string;
  description?: string;
  is_priority?: boolean;
  metric_targets?: MetricTarget[];
  metric_targets_progress?: { metric: string; current: number; target: number; pct: number }[];
}

interface HeatmapData {
  heat_grid: number[][];
  blocks: number;
  steals: number;
  fouls: number;
  total_shots: number;
  made_shots: number;
  fg_pct: number;
  event_count: number;
}

function HeatCourtSVG({ grid }: { grid: number[][] }) {
  const maxVal = Math.max(1, ...grid.flat());
  const ROWS = grid.length;
  const COLS = grid[0]?.length ?? 6;
  const cellW = 500 / COLS;
  const cellH = 280 / ROWS;

  return (
    <svg viewBox="0 0 500 280" className="w-full border border-slate-200 rounded-xl">
      <rect width="500" height="280" fill="#c8a96e" rx="8" />
      {grid.map((row, ri) =>
        row.map((count, ci) => {
          const opacity = count === 0 ? 0 : 0.15 + (count / maxVal) * 0.75;
          return (
            <rect key={`${ri}-${ci}`} x={ci * cellW} y={ri * cellH}
              width={cellW} height={cellH} fill="#ef4444" fillOpacity={opacity} />
          );
        })
      )}
      <circle cx="250" cy="140" r="28" fill="none" stroke="#f5f0e8" strokeWidth="1.5" />
      <line x1="250" y1="2" x2="250" y2="278" stroke="#f5f0e8" strokeWidth="1.5" />
      <rect x="2" y="89" width="95" height="102" fill="none" stroke="#f5f0e8" strokeWidth="1.5" />
      <rect x="403" y="89" width="95" height="102" fill="none" stroke="#f5f0e8" strokeWidth="1.5" />
      <path d="M 2 55 L 95 55 A 120 120 0 0 1 95 225 L 2 225" fill="none" stroke="#f5f0e8" strokeWidth="1.5" />
      <path d="M 498 55 L 405 55 A 120 120 0 0 0 405 225 L 498 225" fill="none" stroke="#f5f0e8" strokeWidth="1.5" />
    </svg>
  );
}

export default function EventHeatmapPage() {
  const params = useParams();
  const router = useRouter();
  const matchupId = params.matchupId as string;

  const [matchupName, setMatchupName] = useState("");
  const [heatmap, setHeatmap] = useState<HeatmapData | null>(null);
  const [liveKeys, setLiveKeys] = useState<LiveKey[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!matchupId) return;
    Promise.all([
      getMatchup(matchupId).then((m) => setMatchupName(m.name)).catch(() => {}),
      getEventHeatmap(matchupId).then(setHeatmap).catch(() => {}),
      getLiveKeysStatus(matchupId).then(setLiveKeys).catch(() => {}),
    ]).finally(() => setLoading(false));
  }, [matchupId, router]);

  const emptyGrid = Array.from({ length: 10 }, () => Array(6).fill(0));

  return (
    <AppShell title="Event Heatmap" subtitle={matchupName || "Game tracking heatmap"}>
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Back link */}
        <Link href={`/game-tracker?matchup=${matchupId}`} className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors">
          <ArrowLeft size={15} /> Back to Game Tracker
        </Link>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 size={24} className="animate-spin text-slate-400" />
          </div>
        ) : (
          <>
            {/* Aggregate stats */}
            {heatmap && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { label: "FG%", value: `${Math.round(heatmap.fg_pct * 100)}%`, sub: `${heatmap.made_shots}/${heatmap.total_shots}` },
                  { label: "Blocks", value: heatmap.blocks },
                  { label: "Steals", value: heatmap.steals },
                  { label: "Fouls", value: heatmap.fouls },
                ].map(({ label, value, sub }) => (
                  <div key={label} className="card text-center">
                    <p className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">{label}</p>
                    <p className="text-3xl font-bold text-slate-900">{value}</p>
                    {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
                  </div>
                ))}
              </div>
            )}

            {/* Heat court */}
            <div className="card">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">Shot Heatmap</p>
              <HeatCourtSVG grid={heatmap?.heat_grid ?? emptyGrid} />
              {!heatmap && (
                <p className="text-center text-sm text-slate-400 mt-4">No shots logged yet for this matchup.</p>
              )}
            </div>

            {/* Keys to Victory cards */}
            {liveKeys.length > 0 && (
              <div className="card">
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">Keys to Victory — Live Progress</p>
                <div className="grid sm:grid-cols-2 gap-3">
                  {liveKeys.map((key) => {
                    const isAtRisk = key.live_status === "at_risk";
                    const isGood = key.live_status === "good";
                    return (
                      <div key={key.key_id} className={clsx("rounded-xl border p-4", {
                        "bg-red-50 border-red-200": isAtRisk,
                        "bg-green-50 border-green-200": isGood,
                        "bg-slate-50 border-slate-200": !isAtRisk && !isGood,
                      })}>
                        <div className="flex items-start justify-between mb-2">
                          <div>
                            {key.is_priority && (
                              <span className="text-[9px] font-bold uppercase tracking-wider text-indigo-600 bg-indigo-50 border border-indigo-200 px-1.5 py-0.5 rounded mb-1 inline-block">
                                Priority
                              </span>
                            )}
                            <p className="text-sm font-bold text-slate-800">{key.title}</p>
                          </div>
                          <span className={clsx("text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded-full border ml-2 shrink-0",
                            isAtRisk ? "bg-red-100 text-red-700 border-red-200" :
                            isGood ? "bg-green-100 text-green-700 border-green-200" :
                            "bg-slate-100 text-slate-600 border-slate-200")}>
                            {isAtRisk ? "AT RISK" : isGood ? "TRACKING" : "ON TRACK"}
                          </span>
                        </div>
                        {key.description && (
                          <p className="text-xs text-slate-600 mb-3">{key.description}</p>
                        )}
                        {/* Metric targets */}
                        {(key.metric_targets_progress ?? key.metric_targets)?.map((mt, i) => {
                          const current = "current" in mt ? mt.current : 0;
                          const target = "target" in mt ? mt.target : 0;
                          const pct = "pct" in mt ? mt.pct : (target > 0 ? current / target : 0);
                          const metric = "metric" in mt ? mt.metric : "";
                          const scope = "scope" in mt ? mt.scope : "";
                          return (
                            <div key={i} className="mb-2">
                              <div className="flex justify-between text-[10px] text-slate-500 mb-1">
                                <span>
                                  {scope && <span className="font-semibold uppercase text-slate-400 mr-1">{scope}:</span>}
                                  {metric.replace(/_/g, " ")}
                                </span>
                                <span className="font-mono">{current} / {target}</span>
                              </div>
                              <div className="h-2 rounded-full bg-slate-200 overflow-hidden">
                                <div
                                  className={clsx("h-full rounded-full transition-all duration-500",
                                    pct >= 1 ? "bg-green-500" : pct >= 0.5 ? "bg-amber-500" : "bg-red-500")}
                                  style={{ width: `${Math.min(100, Math.round(pct * 100))}%` }}
                                />
                              </div>
                            </div>
                          );
                        })}
                        {!key.metric_targets_progress && !key.metric_targets && (
                          <div className="flex items-center gap-1 text-xs text-slate-400">
                            {isGood ? <TrendingUp size={12} className="text-green-500" /> : <TrendingDown size={12} className="text-red-400" />}
                            {key.live_status.replace(/_/g, " ")}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}
