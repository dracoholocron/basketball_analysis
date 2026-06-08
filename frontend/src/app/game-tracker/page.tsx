"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { listMatchups, getMatchup, createGameEvent } from "@/lib/api";
import {
  Activity, CalendarDays, ChevronRight, Loader2, Radio, ArrowLeft,
} from "lucide-react";
import { clsx } from "clsx";

interface Matchup {
  id: string;
  name: string;
  status: string;
  game_date?: string;
  scheduled_at?: string;
}

interface LoggedEvent {
  id: string;
  event_type: string;
  team: number;
  points: number;
  created_at: string;
}

const STATUS_CONFIG: Record<string, { color: string; label: string; dot: string }> = {
  live:      { color: "text-green-400",  label: "En vivo",  dot: "bg-green-400 animate-pulse" },
  pending:   { color: "text-slate-400",  label: "Pendiente", dot: "bg-slate-400" },
  completed: { color: "text-slate-500",  label: "Completado", dot: "bg-slate-600" },
  preparing: { color: "text-amber-400",  label: "Preparando", dot: "bg-amber-400" },
};

function LiveEventPanel({ matchupId }: { matchupId: string }) {
  const [matchupName, setMatchupName] = useState("");
  const [team, setTeam] = useState<1 | 2>(1);
  const [logging, setLogging] = useState(false);
  const [sessionEvents, setSessionEvents] = useState<LoggedEvent[]>([]);

  useEffect(() => {
    getMatchup(matchupId).then((m) => setMatchupName(m.name)).catch(() => {});
  }, [matchupId]);

  async function logEvent(eventType: string, points = 0) {
    setLogging(true);
    try {
      const ev = await createGameEvent(matchupId, {
        event_type: eventType,
        team,
        points,
      });
      setSessionEvents((prev) => [ev, ...prev].slice(0, 5));
    } catch { /* ignore */ }
    finally { setLogging(false); }
  }

  return (
    <div className="space-y-4 mb-8">
      <Link
        href="/game-tracker"
        className="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-white transition-colors"
      >
        <ArrowLeft size={15} /> All matchups
      </Link>

      <div className="rounded-xl border border-slate-600 bg-slate-800 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <p className="text-xs uppercase tracking-wider text-slate-500">Live logging</p>
            <h2 className="text-lg font-semibold text-white">{matchupName || "Matchup"}</h2>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Team</span>
            {([1, 2] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTeam(t)}
                className={clsx(
                  "px-3 py-1.5 rounded-lg text-xs font-semibold",
                  team === t ? "bg-blue-600 text-white" : "bg-slate-700 text-slate-300 hover:bg-slate-600",
                )}
              >
                T{t}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          <button
            type="button"
            disabled={logging}
            onClick={() => logEvent("shot_attempt", 0)}
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium disabled:opacity-50"
          >
            Shot attempt
          </button>
          <button
            type="button"
            disabled={logging}
            onClick={() => logEvent("rebound", 0)}
            className="px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-white text-sm font-medium disabled:opacity-50"
          >
            Rebound
          </button>
          <button
            type="button"
            disabled={logging}
            onClick={() => logEvent("turnover", 0)}
            className="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium disabled:opacity-50"
          >
            Turnover
          </button>
          <Link
            href={`/game-tracker/${matchupId}/event-heatmap`}
            className="px-4 py-2 rounded-lg border border-slate-600 text-slate-300 hover:text-white text-sm font-medium"
          >
            Heatmap →
          </Link>
        </div>

        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Last 5 (this session)</p>
        {sessionEvents.length === 0 ? (
          <p className="text-sm text-slate-500">No events logged yet.</p>
        ) : (
          <ul className="divide-y divide-slate-700 rounded-lg border border-slate-700 overflow-hidden">
            {sessionEvents.map((ev) => (
              <li key={ev.id} className="flex items-center gap-3 px-3 py-2 text-sm bg-slate-900/40">
                <span className={clsx(
                  "h-6 w-6 rounded-full text-white text-[10px] font-bold flex items-center justify-center",
                  ev.team === 1 ? "bg-blue-500" : "bg-violet-500",
                )}>
                  T{ev.team}
                </span>
                <span className="text-slate-200 flex-1">{ev.event_type.replace(/_/g, " ")}</span>
                <span className="text-xs text-slate-500">
                  {new Date(ev.created_at).toLocaleTimeString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function GameTrackerContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedMatchupId = searchParams.get("matchup");

  const [matchups, setMatchups] = useState<Matchup[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listMatchups(0, 50)
      .then(data => setMatchups(Array.isArray(data) ? data : data.items ?? []))
      .catch(() => router.replace("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  const liveMatchups     = matchups.filter(m => m.status === "live");
  const upcomingMatchups = matchups.filter(m => m.status !== "live" && m.status !== "completed");
  const pastMatchups     = matchups.filter(m => m.status === "completed");

  return (
    <AppShell title="Game Tracker" subtitle="Marcador en vivo y análisis de eventos">
      <div className="max-w-4xl mx-auto space-y-8">
        {selectedMatchupId && <LiveEventPanel matchupId={selectedMatchupId} />}

        {loading ? (
          <div className="flex justify-center py-20">
            <Loader2 className="animate-spin text-blue-500" size={32} />
          </div>
        ) : matchups.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-slate-500 gap-3">
            <CalendarDays size={48} className="opacity-30" />
            <p className="text-sm">Sin partidos registrados.</p>
            <Link href="/game-day" className="text-blue-400 hover:underline text-sm">
              Crear partido en Game Day →
            </Link>
          </div>
        ) : (
          <>
            {liveMatchups.length > 0 && (
              <section>
                <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">
                  <Radio size={14} className="text-green-400 animate-pulse" /> En vivo
                </h2>
                <div className="space-y-3">
                  {liveMatchups.map(m => (
                    <MatchupCard key={m.id} matchup={m} accent />
                  ))}
                </div>
              </section>
            )}

            {upcomingMatchups.length > 0 && (
              <section>
                <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">
                  <CalendarDays size={14} /> Próximos
                </h2>
                <div className="space-y-2">
                  {upcomingMatchups.map(m => (
                    <MatchupCard key={m.id} matchup={m} />
                  ))}
                </div>
              </section>
            )}

            {pastMatchups.length > 0 && (
              <section>
                <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-400 uppercase tracking-wide mb-3">
                  <Activity size={14} /> Completados
                </h2>
                <div className="space-y-2">
                  {pastMatchups.map(m => (
                    <MatchupCard key={m.id} matchup={m} />
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}

function MatchupCard({ matchup, accent = false }: { matchup: Matchup; accent?: boolean }) {
  const cfg = STATUS_CONFIG[matchup.status] ?? STATUS_CONFIG.pending;
  return (
    <div className={clsx(
      "flex items-center justify-between p-4 rounded-xl border transition-colors",
      accent
        ? "bg-green-900/20 border-green-700/40 hover:border-green-600/60"
        : "bg-slate-800 border-slate-700 hover:border-slate-500",
    )}>
      <div className="flex items-center gap-3">
        <span className={clsx("w-2.5 h-2.5 rounded-full", cfg.dot)} />
        <div>
          <p className="font-semibold text-white text-sm">{matchup.name}</p>
          <p className="text-xs text-slate-400 mt-0.5">
            {matchup.game_date ?? matchup.scheduled_at?.slice(0, 10) ?? "Sin fecha"}
            <span className={clsx("ml-2 font-medium", cfg.color)}>{cfg.label}</span>
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Link
          href={`/game-tracker?matchup=${matchup.id}`}
          className="flex items-center gap-1 px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium"
        >
          <Activity size={12} /> Log events
        </Link>
        <Link
          href={`/game-tracker/${matchup.id}/event-heatmap`}
          className="flex items-center gap-1 px-3 py-1.5 text-xs bg-slate-700 hover:bg-slate-600 text-white rounded-lg font-medium"
        >
          Heatmap
        </Link>
        <Link
          href={`/matchups/${matchup.id}`}
          className="p-1.5 text-slate-400 hover:text-white"
        >
          <ChevronRight size={16} />
        </Link>
      </div>
    </div>
  );
}

export default function GameTrackerPage() {
  return (
    <Suspense fallback={
      <AppShell title="Game Tracker">
        <div className="flex justify-center py-20">
          <Loader2 className="animate-spin text-blue-500" size={32} />
        </div>
      </AppShell>
    }>
      <GameTrackerContent />
    </Suspense>
  );
}



