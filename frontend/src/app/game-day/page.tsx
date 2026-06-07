"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import {
  listMatchups, createMatchup, getPrepStatus, listTeams,
  getSimulation,
} from "@/lib/api";
import {
  CalendarDays, CheckCircle2, Circle, Loader2, PlusCircle,
  ChevronRight, Target, BookOpen, PenTool, Activity, Trophy,
  AlertCircle,
} from "lucide-react";
import { clsx } from "clsx";

interface Team { id: string; name: string; }
interface Matchup {
  id: string; name: string; status: string;
  scheduled_at?: string; game_date?: string;
  own_team_id?: string; opponent_team_id?: string;
}
interface PrepStep { id: string; name: string; complete: boolean; link: string; }
interface PrepStatus {
  matchup_id: string; matchup_name: string; steps: PrepStep[];
  win_probability_us: number | null; progress_pct: number;
}

const STEP_ICONS: Record<string, React.ReactNode> = {
  scouting:   <BookOpen size={15} />,
  sim:        <Target size={15} />,
  plays:      <PenTool size={15} />,
  video:      <Activity size={15} />,
  box_scores: <Trophy size={15} />,
};

function WinRing({ pct }: { pct: number }) {
  const r = 30, c = 2 * Math.PI * r;
  return (
    <svg width="80" height="80" viewBox="0 0 80 80">
      <circle cx="40" cy="40" r={r} fill="none" stroke="#1e293b" strokeWidth="8" />
      <circle
        cx="40" cy="40" r={r} fill="none" stroke={pct >= 60 ? "#22c55e" : pct >= 40 ? "#f59e0b" : "#ef4444"}
        strokeWidth="8" strokeDasharray={`${(pct / 100) * c} ${c}`}
        strokeLinecap="round" transform="rotate(-90 40 40)"
      />
      <text x="40" y="44" textAnchor="middle" fontSize="14" fontWeight="bold" fill="white">{pct}%</text>
    </svg>
  );
}

export default function GameDayPage() {
  return (
    <Suspense>
      <GameDayContent />
    </Suspense>
  );
}

function GameDayContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselect = searchParams.get("matchup");

  const [matchups, setMatchups] = useState<Matchup[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [selected, setSelected] = useState<string | null>(preselect);
  const [prep, setPrep] = useState<PrepStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [prepLoading, setPrepLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", own_team_id: "", opponent_team_id: "", game_date: "" });

  useEffect(() => {
    Promise.all([
      listMatchups().catch(() => []),
      listTeams().then(d => d.items ?? d).catch(() => []),
    ]).then(([m, t]) => {
      setMatchups(m);
      setTeams(t);
    }).catch(() => router.replace("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  useEffect(() => {
    if (!selected) return;
    setPrepLoading(true);
    getPrepStatus(selected)
      .then(setPrep)
      .catch(() => setPrep(null))
      .finally(() => setPrepLoading(false));
  }, [selected]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      const m = await createMatchup(form);
      setMatchups(prev => [m, ...prev]);
      setSelected(m.id);
      setShowForm(false);
    } catch {
      /* ignore */
    } finally {
      setCreating(false);
    }
  }

  const teamName = (id?: string) => teams.find(t => t.id === id)?.name ?? "—";
  const completedSteps = prep?.steps.filter(s => s.complete).length ?? 0;
  const totalSteps = prep?.steps.length ?? 0;

  return (
    <AppShell title="Game Day Prep" subtitle="Prepara el partido desde un solo lugar">
      <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Left: Matchup list */}
        <div className="lg:col-span-1 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wide">Partidos</h2>
            <button
              onClick={() => setShowForm(v => !v)}
              className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300"
            >
              <PlusCircle size={14} /> Nuevo
            </button>
          </div>

          {showForm && (
            <form onSubmit={handleCreate} className="bg-slate-800 rounded-xl p-4 space-y-3">
              <input
                placeholder="Nombre del partido"
                value={form.name}
                onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                className="w-full bg-slate-700 text-white text-sm rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
              <select
                value={form.own_team_id}
                onChange={e => setForm(p => ({ ...p, own_team_id: e.target.value }))}
                className="w-full bg-slate-700 text-white text-sm rounded-lg px-3 py-2"
              >
                <option value="">Mi equipo…</option>
                {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
              <select
                value={form.opponent_team_id}
                onChange={e => setForm(p => ({ ...p, opponent_team_id: e.target.value }))}
                className="w-full bg-slate-700 text-white text-sm rounded-lg px-3 py-2"
              >
                <option value="">Rival…</option>
                {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
              <input
                type="date"
                value={form.game_date}
                onChange={e => setForm(p => ({ ...p, game_date: e.target.value }))}
                className="w-full bg-slate-700 text-white text-sm rounded-lg px-3 py-2"
              />
              <button
                type="submit"
                disabled={creating || !form.name}
                className="w-full py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium disabled:opacity-50"
              >
                {creating ? <Loader2 size={14} className="animate-spin inline mr-1" /> : null}
                Crear partido
              </button>
            </form>
          )}

          {loading ? (
            <div className="flex justify-center py-8"><Loader2 className="animate-spin text-blue-500" /></div>
          ) : matchups.length === 0 ? (
            <div className="text-center py-10 text-slate-500 text-sm">
              <CalendarDays size={36} className="mx-auto mb-2 opacity-30" />
              Sin partidos. Crea el primero.
            </div>
          ) : (
            <div className="space-y-2">
              {matchups.map(m => (
                <button
                  key={m.id}
                  onClick={() => setSelected(m.id)}
                  className={clsx(
                    "w-full text-left px-4 py-3 rounded-xl transition-colors flex items-center justify-between group",
                    selected === m.id
                      ? "bg-blue-600 text-white"
                      : "bg-slate-800 text-slate-300 hover:bg-slate-700",
                  )}
                >
                  <div>
                    <p className="font-medium text-sm">{m.name}</p>
                    <p className="text-xs opacity-70 mt-0.5">
                      {m.game_date ?? m.scheduled_at?.slice(0, 10) ?? "Sin fecha"}
                    </p>
                  </div>
                  <ChevronRight size={16} className="opacity-50 group-hover:opacity-100" />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right: Prep dashboard */}
        <div className="lg:col-span-2">
          {!selected ? (
            <div className="flex flex-col items-center justify-center h-64 text-slate-500 bg-slate-800 rounded-2xl">
              <CalendarDays size={48} className="mb-3 opacity-30" />
              <p className="text-sm">Selecciona un partido para ver la preparación.</p>
            </div>
          ) : prepLoading ? (
            <div className="flex justify-center items-center h-64 bg-slate-800 rounded-2xl">
              <Loader2 className="animate-spin text-blue-500" size={32} />
            </div>
          ) : prep ? (
            <div className="space-y-5">
              {/* Header */}
              <div className="bg-slate-800 rounded-2xl p-6 flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold text-white">{prep.matchup_name}</h2>
                  <p className="text-sm text-slate-400 mt-1">
                    {completedSteps}/{totalSteps} pasos completados
                  </p>
                  <div className="w-48 h-1.5 bg-slate-700 rounded-full mt-3">
                    <div
                      className="h-full bg-blue-500 rounded-full transition-all"
                      style={{ width: `${prep.progress_pct}%` }}
                    />
                  </div>
                </div>
                {prep.win_probability_us !== null && (
                  <div className="text-center">
                    <WinRing pct={Math.round((prep.win_probability_us ?? 0.5) * 100)} />
                    <p className="text-xs text-slate-400 mt-1">Prob. victoria</p>
                  </div>
                )}
              </div>

              {/* Steps */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {prep.steps.map(step => (
                  <Link
                    key={step.id}
                    href={step.link || "#"}
                    className={clsx(
                      "flex items-center gap-3 p-4 rounded-xl transition-colors",
                      step.complete
                        ? "bg-green-900/20 border border-green-700/40"
                        : "bg-slate-800 border border-slate-700 hover:border-slate-500",
                    )}
                  >
                    <span className={step.complete ? "text-green-400" : "text-slate-500"}>
                      {step.complete ? <CheckCircle2 size={20} /> : <Circle size={20} />}
                    </span>
                    <span className={clsx("text-slate-400", step.complete && "opacity-60")}>
                      {STEP_ICONS[step.id] ?? <Activity size={15} />}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className={clsx("text-sm font-medium", step.complete ? "text-green-400 line-through" : "text-white")}>
                        {step.name}
                      </p>
                    </div>
                    <ChevronRight size={14} className="text-slate-600 shrink-0" />
                  </Link>
                ))}
              </div>

              {/* Quick actions */}
              <div className="flex flex-wrap gap-3">
                <Link
                  href={`/scouting?matchup=${selected}`}
                  className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm"
                >
                  <BookOpen size={14} /> Scouting
                </Link>
                <Link
                  href={`/matchups/${selected}`}
                  className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm"
                >
                  <Target size={14} /> Simulación
                </Link>
                <Link
                  href={`/play-builder?matchup=${selected}`}
                  className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm"
                >
                  <PenTool size={14} /> Jugadas
                </Link>
                <Link
                  href={`/game-tracker/${selected}/event-heatmap`}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium"
                >
                  <Activity size={14} /> Live Tracker
                </Link>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-64 bg-slate-800 rounded-2xl gap-3 text-slate-400">
              <AlertCircle size={36} className="opacity-40" />
              <p className="text-sm">No se pudo cargar el estado de preparación.</p>
              <button
                onClick={() => { setPrepLoading(true); getPrepStatus(selected!).then(setPrep).catch(() => null).finally(() => setPrepLoading(false)); }}
                className="text-xs text-blue-400 hover:underline"
              >
                Reintentar
              </button>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
