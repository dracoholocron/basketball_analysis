"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { listGames, listJobs, listSeasons, getUpcomingMatchups, getPrepStatus } from "@/lib/api";
import {
  Video,
  Layers,
  Trophy,
  ArrowRight,
  TrendingUp,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  PlusCircle,
  Search,
  CalendarDays,
  BarChart3,
  Swords,
} from "lucide-react";
import { clsx } from "clsx";

interface UpcomingMatchup {
  id: string; name: string; scheduled_at?: string; status: string;
}

interface PrepStep { id: string; name: string; complete: boolean; link: string; }
interface PrepStatus {
  matchup_id: string; matchup_name: string; steps: PrepStep[];
  win_probability_us: number | null; progress_pct: number;
}

const STEP_LABELS_SHORT = ["Scouting", "Simulation", "Game Plan", "Plays", "Tracker"];

function WeeklyRhythmWidget({ matchup }: { matchup: UpcomingMatchup }) {
  const [prep, setPrep] = useState<PrepStatus | null>(null);
  useEffect(() => {
    getPrepStatus(matchup.id).then(setPrep).catch(() => {});
  }, [matchup.id]);

  const winPct = Math.round((prep?.win_probability_us ?? 0.5) * 100);
  const steps = prep?.steps ?? [];

  return (
    <Link href={`/matchups/${matchup.id}`} className="card hover:shadow-card-hover transition-all block">
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="text-sm font-bold text-slate-800 leading-tight">{matchup.name}</p>
          {matchup.scheduled_at && (
            <p className="text-[10px] text-slate-400 mt-0.5">
              {new Date(matchup.scheduled_at).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}
            </p>
          )}
        </div>
        {prep?.win_probability_us != null && (
          <div className="text-right">
            <p className="text-xl font-bold text-slate-800">{winPct}<span className="text-xs text-slate-400">%</span></p>
            <p className="text-[9px] text-slate-400">win prob</p>
          </div>
        )}
      </div>

      {/* 5-step stepper */}
      <div className="flex items-center gap-1 mb-3">
        {(steps.length > 0 ? steps : STEP_LABELS_SHORT.map((name, i) => ({ id: String(i), name, complete: false, link: "#" }))).map((step, i, arr) => (
          <div key={step.id} className="flex items-center flex-1">
            <div className="flex flex-col items-center w-full">
              <div className={clsx("h-5 w-5 rounded-full flex items-center justify-center border",
                step.complete ? "bg-green-500 border-green-500 text-white" : "bg-white border-slate-200 text-slate-300")}>
                {step.complete ? <CheckCircle2 size={11} /> : <span className="text-[8px] font-bold">{i + 1}</span>}
              </div>
              <p className="text-[8px] text-slate-400 text-center mt-0.5 leading-tight">{step.name}</p>
            </div>
            {i < arr.length - 1 && (
              <div className={clsx("h-px flex-1 mb-3", step.complete ? "bg-green-400" : "bg-slate-100")} />
            )}
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div className="h-1.5 rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-green-500 transition-all" style={{ width: `${prep?.progress_pct ?? 0}%` }} />
      </div>
      <p className="text-[9px] text-slate-400 text-right mt-1">{prep?.progress_pct ?? 0}% ready</p>
    </Link>
  );
}

interface Job {
  id: string;
  game_id: string;
  status: string;
  current_stage: string;
  progress_pct: number;
  created_at: string;
  finished_at: string | null;
}

const STATUS_ICON: Record<string, React.ReactNode> = {
  done: <CheckCircle2 size={14} className="text-success-500" />,
  failed: <XCircle size={14} className="text-danger-500" />,
  running: <Loader2 size={14} className="text-primary-500 animate-spin" />,
  pending: <Clock size={14} className="text-slate-400" />,
};

const QUICK_ACTIONS = [
  {
    label: "New Game",
    description: "Record a game and upload video",
    href: "/games",
    icon: <Video size={20} className="text-primary-600" />,
    accent: "bg-primary-50 border-primary-100",
  },
  {
    label: "Scout Opponent",
    description: "AI-powered scouting report",
    href: "/scouting",
    icon: <Search size={20} className="text-violet-600" />,
    accent: "bg-violet-50 border-violet-100",
  },
  {
    label: "Game Day Prep",
    description: "Keys to Victory & simulation",
    href: "/game-day",
    icon: <CalendarDays size={20} className="text-success-600" />,
    accent: "bg-success-50 border-success-100",
  },
  {
    label: "Matchup Workspace",
    description: "Scouting, plays, and live tracker",
    href: "/matchups",
    icon: <BarChart3 size={20} className="text-warning-600" />,
    accent: "bg-warning-50 border-warning-100",
  },
];

export default function DashboardPage() {
  const router = useRouter();
  const [gamesTotal, setGamesTotal] = useState<number | null>(null);
  const [recentJobs, setRecentJobs] = useState<Job[]>([]);
  const [seasonsTotal, setSeasonsTotal] = useState<number | null>(null);
  const [upcomingMatchups, setUpcomingMatchups] = useState<UpcomingMatchup[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const auth = Promise.all([
      listGames(0, 5).then((d) => {
        setGamesTotal(d.total ?? d.items?.length ?? 0);
      }),
      listJobs(0, 6).then((d) => {
        const items = Array.isArray(d) ? d : d.items ?? [];
        setRecentJobs(items);
      }),
      listSeasons(0, 50).then((d) => {
        const items = d.items ?? d;
        setSeasonsTotal(items.length);
      }),
      getUpcomingMatchups().then(setUpcomingMatchups).catch(() => {}),
    ]).catch(() => router.replace("/login"));

    auth.finally(() => setLoading(false));
  }, [router]);

  const doneJobs = recentJobs.filter((j) => j.status === "done").length;
  const runningJobs = recentJobs.filter(
    (j) => j.status === "running" || j.status === "pending"
  ).length;

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto space-y-8">
        {/* Hero banner */}
        <div className="rounded-2xl bg-gradient-to-br from-primary-700 to-primary-900 p-8 text-white relative overflow-hidden">
          <div className="absolute inset-0 opacity-10" style={{ backgroundImage: "radial-gradient(circle at 80% 50%, #fff 0%, transparent 60%)" }} />
          <div className="relative">
            <p className="text-primary-200 text-sm font-semibold uppercase tracking-wider mb-2">Welcome back, Coach</p>
            <h1 className="font-display text-3xl font-bold mb-2">Basketball IQ Dashboard</h1>
            <p className="text-primary-100 text-sm max-w-lg">
              AI-powered video analysis, scouting reports and game simulation — all in one place.
            </p>
            <Link href="/games" className="mt-5 inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-primary-700 hover:bg-primary-50 transition-colors">
              <PlusCircle size={16} />
              New Game
              <ArrowRight size={14} />
            </Link>
          </div>
        </div>

        {/* KPI cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label: "Total Games", value: loading ? "—" : gamesTotal ?? 0, icon: <Video size={18} />, color: "text-primary-600", bg: "bg-primary-50" },
            { label: "Active Seasons", value: loading ? "—" : seasonsTotal ?? 0, icon: <Trophy size={18} />, color: "text-success-600", bg: "bg-success-50" },
            { label: "Analysis Jobs", value: loading ? "—" : recentJobs.length, icon: <Layers size={18} />, color: "text-violet-600", bg: "bg-violet-50" },
            { label: "In Progress", value: loading ? "—" : runningJobs, icon: <TrendingUp size={18} />, color: "text-warning-600", bg: "bg-warning-50" },
          ].map((kpi) => (
            <div key={kpi.label} className="card flex items-center gap-4">
              <div className={clsx("h-10 w-10 rounded-xl flex items-center justify-center flex-shrink-0", kpi.bg, kpi.color)}>
                {kpi.icon}
              </div>
              <div>
                <p className="text-2xl font-bold text-slate-900">{kpi.value}</p>
                <p className="text-xs text-slate-500 mt-0.5">{kpi.label}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Weekly Rhythm Widget (M2) */}
        {upcomingMatchups.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Swords size={18} className="text-indigo-500" />
                <h2 className="text-lg font-bold text-slate-900 font-display">Upcoming Matchups</h2>
              </div>
              <Link href="/matchups" className="text-sm text-primary-600 hover:text-primary-700 font-medium flex items-center gap-1">
                All matchups <ArrowRight size={14} />
              </Link>
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {upcomingMatchups.slice(0, 3).map(m => (
                <WeeklyRhythmWidget key={m.id} matchup={m} />
              ))}
            </div>
          </div>
        )}

        {/* Quick actions */}
        <div>
          <h2 className="text-lg font-bold text-slate-900 mb-4 font-display">Quick Actions</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {QUICK_ACTIONS.map((action) => (
              <Link
                key={action.label}
                href={action.href}
                className={clsx(
                  "relative block rounded-xl border p-4 hover:shadow-card-hover transition-all duration-150",
                  action.accent,
                )}
              >
                <div className="mb-3">{action.icon}</div>
                <p className="font-semibold text-sm text-slate-800">{action.label}</p>
                <p className="text-xs text-slate-500 mt-0.5">{action.description}</p>
              </Link>
            ))}
          </div>
        </div>

        {/* Recent jobs */}
        {!loading && recentJobs.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-slate-900 font-display">Recent Analysis Jobs</h2>
              <Link href="/jobs" className="text-sm text-primary-600 hover:text-primary-700 font-medium flex items-center gap-1">
                View all <ArrowRight size={14} />
              </Link>
            </div>
            <div className="card p-0 overflow-hidden">
              {recentJobs.map((job, i) => (
                <div key={job.id} className={clsx("flex items-center gap-4 px-5 py-3.5 text-sm", i !== 0 && "border-t border-slate-50")}>
                  <div>{STATUS_ICON[job.status] ?? STATUS_ICON.pending}</div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-slate-800 capitalize">
                      {job.current_stage.replace(/_/g, " ")}
                    </p>
                    <p className="text-xs text-slate-400 truncate font-mono">{job.game_id}</p>
                  </div>
                  <div className="text-right">
                    <span className={clsx(
                      "badge capitalize",
                      job.status === "done" ? "badge-green" :
                      job.status === "failed" ? "badge-red" :
                      job.status === "running" ? "badge-blue" : "badge-gray"
                    )}>
                      {job.status}
                    </span>
                    <p className="text-[10px] text-slate-400 mt-1">
                      {new Date(job.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  {job.status === "done" && (
                    <Link href={`/games/${job.game_id}`} className="text-primary-600 hover:text-primary-700">
                      <ArrowRight size={16} />
                    </Link>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!loading && recentJobs.length === 0 && gamesTotal === 0 && (
          <div className="card text-center py-16">
            <div className="mx-auto mb-4 h-16 w-16 rounded-2xl bg-primary-50 flex items-center justify-center">
              <Video size={28} className="text-primary-600" />
            </div>
            <h3 className="font-display text-lg font-bold text-slate-900 mb-2">Get started</h3>
            <p className="text-slate-500 text-sm max-w-sm mx-auto mb-6">
              Create your first game, upload a video, and let the AI analyze player performance for you.
            </p>
            <Link href="/games" className="btn-primary inline-flex">
              <PlusCircle size={16} />
              Create First Game
            </Link>
          </div>
        )}
      </div>
    </AppShell>
  );
}
