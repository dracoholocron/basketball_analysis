"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { listMatchups } from "@/lib/api";
import {
  Activity, CalendarDays, ChevronRight, Loader2, Radio,
} from "lucide-react";
import { clsx } from "clsx";

interface Matchup {
  id: string;
  name: string;
  status: string;
  game_date?: string;
  scheduled_at?: string;
}

const STATUS_CONFIG: Record<string, { color: string; label: string; dot: string }> = {
  live:      { color: "text-green-400",  label: "En vivo",  dot: "bg-green-400 animate-pulse" },
  pending:   { color: "text-slate-400",  label: "Pendiente", dot: "bg-slate-400" },
  completed: { color: "text-slate-500",  label: "Completado", dot: "bg-slate-600" },
  preparing: { color: "text-amber-400",  label: "Preparando", dot: "bg-amber-400" },
};

export default function GameTrackerPage() {
  const router = useRouter();
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
            {/* Live */}
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

            {/* Upcoming */}
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

            {/* Past */}
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
          href={`/game-tracker/${matchup.id}/event-heatmap`}
          className="flex items-center gap-1 px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium"
        >
          <Activity size={12} /> Tracker
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
