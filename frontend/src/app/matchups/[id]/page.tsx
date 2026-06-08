"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import {
  getMatchup, getPrepStatus, getSimulation, runSimulation, listPlays, updateMatchupNotes,
  listGameEvents, setPriorityKey,
} from "@/lib/api";
import {
  Loader2, ArrowLeft, Activity, Target, BookOpen, PenTool, MapPin,
  StickyNote, CheckCircle2, Circle, ChevronRight, TrendingUp,
} from "lucide-react";
import { clsx } from "clsx";
import { useCoachMode } from "@/contexts/CoachModeContext";

interface Matchup {
  id: string; name: string; own_team_id?: string; opponent_team_id?: string;
  scheduled_at?: string; status: string; notes?: Record<string, unknown> | null;
  game_config?: Record<string, unknown>;
}

interface PrepStep { id: string; name: string; complete: boolean; link: string; }
interface PrepStatus {
  matchup_id: string; matchup_name: string; steps: PrepStep[];
  win_probability_us: number | null; progress_pct: number;
}

interface Key {
  id: string; title: string; description?: string; is_priority: boolean;
  priority_rank?: number; coefficient?: number; live_status?: string;
}

interface SimulationData {
  id: string;
  win_pct_own: number;
  avg_score_own: number | null;
  avg_score_opp: number | null;
  keys?: Key[];
}

type TabId = "overview" | "scouting" | "simulation" | "plays" | "tracker" | "notes";

const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: "overview", label: "Overview", icon: <MapPin size={14} /> },
  { id: "scouting", label: "Scouting", icon: <BookOpen size={14} /> },
  { id: "simulation", label: "Simulation", icon: <Target size={14} /> },
  { id: "plays", label: "Plays", icon: <PenTool size={14} /> },
  { id: "tracker", label: "Live Tracker", icon: <Activity size={14} /> },
  { id: "notes", label: "Notes", icon: <StickyNote size={14} /> },
];

function WinRing({ pct }: { pct: number }) {
  const radius = 36;
  const circumference = 2 * Math.PI * radius;
  const dash = (pct / 100) * circumference;
  return (
    <svg width="90" height="90" viewBox="0 0 90 90">
      <circle cx="45" cy="45" r={radius} fill="none" stroke="#e2e8f0" strokeWidth="8" />
      <circle cx="45" cy="45" r={radius} fill="none" stroke={pct >= 55 ? "#22c55e" : pct >= 45 ? "#f59e0b" : "#ef4444"}
        strokeWidth="8" strokeDasharray={`${dash} ${circumference}`} strokeDashoffset={circumference * 0.25} strokeLinecap="round" />
      <text x="45" y="49" textAnchor="middle" className="text-sm" fontSize="16" fontWeight="700" fill="#1e293b">{pct}%</text>
    </svg>
  );
}

function MatchupWorkspaceContent() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { coachMode } = useCoachMode();

  const [matchup, setMatchup] = useState<Matchup | null>(null);
  const [prepStatus, setPrepStatus] = useState<PrepStatus | null>(null);
  const [keys, setKeys] = useState<Key[]>([]);
  const [recentEvents, setRecentEvents] = useState<unknown[]>([]);
  const [plays, setPlays] = useState<unknown[]>([]);
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [savingNotes, setSavingNotes] = useState(false);
  const [simulation, setSimulation] = useState<SimulationData | null>(null);
  const [simRunning, setSimRunning] = useState(false);

  const tabParam = (searchParams.get("tab") as TabId) || "overview";
  const [activeTab, setActiveTab] = useState<TabId>(tabParam);

  const fetchData = useCallback(async () => {
    try {
      const [m, prep] = await Promise.all([getMatchup(id), getPrepStatus(id).catch(() => null)]);
      setMatchup(m);
      setPrepStatus(prep);
      if (m.notes && typeof m.notes === "object") {
        setNotes((m.notes as Record<string, string>).text ?? "");
      }
      getSimulation(id).then((sim) => {
        if (sim) {
          setSimulation(sim);
          setKeys(sim.keys ?? []);
        }
      }).catch(() => {});
      // Fetch recent events
      listGameEvents(id, 0, 10).then(setRecentEvents).catch(() => {});
      // Fetch linked plays
      listPlays(id, 0, 20).then((p: unknown[]) => setPlays(Array.isArray(p) ? p : [])).catch(() => {});
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 401 || status === 403) {
        router.replace("/login");
      } else {
        setMatchup(null);
      }
    }
    finally { setLoading(false); }
  }, [id, router]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Autosave notes
  useEffect(() => {
    if (!matchup || notes === ((matchup.notes as Record<string, string> | null)?.text ?? "")) return;
    const t = setTimeout(async () => {
      setSavingNotes(true);
      try { await updateMatchupNotes(id, { notes: { text: notes } }); }
      catch { /* ignore */ }
      finally { setSavingNotes(false); }
    }, 1000);
    return () => clearTimeout(t);
  }, [notes, id, matchup]);

  async function loadSimulation() {
    const sim = await getSimulation(id);
    if (sim) {
      setSimulation(sim);
      setKeys(sim.keys ?? []);
    } else {
      setSimulation(null);
      setKeys([]);
    }
  }

  async function handleRunSimulation() {
    setSimRunning(true);
    try {
      await runSimulation(id);
      await loadSimulation();
    } catch { /* ignore */ }
    finally { setSimRunning(false); }
  }

  async function toggleKeyPriority(key: Key) {
    const next = !key.is_priority;
    const rank = next ? (priorityKeys.length + 1) : undefined;
    try {
      await setPriorityKey(id, key.id, next, rank);
      await loadSimulation();
    } catch { /* ignore */ }
  }

  function switchTab(tab: TabId) {
    setActiveTab(tab);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", tab);
    window.history.pushState({}, "", url.toString());
  }

  const priorityKeys = keys.filter(k => k.is_priority).sort((a, b) => (a.priority_rank ?? 99) - (b.priority_rank ?? 99));
  const winPct = Math.round((prepStatus?.win_probability_us ?? 0.5) * 100);

  if (loading) {
    return (
      <AppShell title="Matchup Workspace">
        <div className="flex items-center justify-center py-20"><Loader2 size={24} className="animate-spin text-slate-400" /></div>
      </AppShell>
    );
  }

  if (!matchup) {
    return (
      <AppShell title="Matchup Workspace">
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <p className="text-2xl font-bold text-slate-700">Matchup not found</p>
          <p className="text-slate-400">This matchup does not exist or has been deleted.</p>
          <Link href="/matchups" className="btn-primary btn-sm">Back to Matchups</Link>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell title="Matchup Workspace" subtitle={matchup.name}>
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center gap-4 mb-4">
          <Link href="/matchups" className="text-slate-400 hover:text-slate-600"><ArrowLeft size={18} /></Link>
          <div className="flex-1">
            <h2 className="text-xl font-bold text-slate-900">{matchup.name}</h2>
            {matchup.scheduled_at && (
              <p className="text-xs text-slate-400">{new Date(matchup.scheduled_at).toLocaleDateString()}</p>
            )}
          </div>
          {prepStatus?.win_probability_us != null && (
            <div className="flex items-center gap-3">
              <WinRing pct={winPct} />
              <div>
                <p className="text-[10px] uppercase tracking-wider text-slate-400">Win Probability</p>
                <p className="text-sm font-bold text-slate-700">
                  {coachMode ? `${Math.round(winPct / 10)} in 10` : `${winPct}%`}
                </p>
              </div>
            </div>
          )}
          <Link href={`/game-tracker?matchup=${id}`} className="btn-primary btn-sm">
            <Activity size={13} /> Live Tracker
          </Link>
        </div>

        <div className="grid lg:grid-cols-[1fr_280px] gap-5">
          {/* Main area */}
          <div>
            {/* Tabs */}
            <div className="flex gap-1 border-b border-slate-200 mb-5 overflow-x-auto">
              {TABS.map((tab) => (
                <button key={tab.id} onClick={() => switchTab(tab.id)}
                  className={clsx("flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap",
                    activeTab === tab.id ? "border-primary-500 text-primary-600" : "border-transparent text-slate-500 hover:text-slate-700")}>
                  {tab.icon}{tab.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            {activeTab === "overview" && (
              <div className="space-y-4">
                {/* Prep status stepper */}
                {prepStatus && (
                  <div className="card">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">Weekly Prep Progress</p>
                    <div className="flex items-center gap-0">
                      {prepStatus.steps.map((step, i) => (
                        <div key={step.id} className="flex items-center flex-1">
                          <Link href={step.link} className="flex flex-col items-center gap-1 flex-1 text-center group">
                            <div className={clsx("h-8 w-8 rounded-full flex items-center justify-center border-2 transition-colors",
                              step.complete ? "bg-green-500 border-green-500 text-white" : "bg-white border-slate-200 text-slate-400 group-hover:border-primary-300")}>
                              {step.complete ? <CheckCircle2 size={16} /> : <span className="text-xs font-bold">{i + 1}</span>}
                            </div>
                            <p className="text-[10px] text-slate-500 leading-tight max-w-[80px]">{step.name}</p>
                          </Link>
                          {i < prepStatus.steps.length - 1 && (
                            <div className={clsx("h-0.5 flex-1 mx-1", step.complete ? "bg-green-400" : "bg-slate-200")} />
                          )}
                        </div>
                      ))}
                    </div>
                    <div className="mt-3 h-2 rounded-full bg-slate-100">
                      <div className="h-full rounded-full bg-green-500 transition-all" style={{ width: `${prepStatus.progress_pct}%` }} />
                    </div>
                    <p className="text-xs text-slate-400 mt-1 text-right">{prepStatus.progress_pct}% complete</p>
                  </div>
                )}

                {/* Top 3 Keys */}
                {priorityKeys.length > 0 && (
                  <div className="card">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">Top 3 Priorities</p>
                    <div className="space-y-2">
                      {priorityKeys.map((key, i) => (
                        <div key={key.id} className="flex items-start gap-3 p-3 rounded-xl border border-indigo-100 bg-indigo-50">
                          <span className="h-7 w-7 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-bold flex-shrink-0">
                            {i + 1}
                          </span>
                          <div>
                            <p className="text-sm font-bold text-slate-800">{key.title}</p>
                            {!coachMode && key.description && <p className="text-xs text-slate-500">{key.description}</p>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === "plays" && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-slate-700">{plays.length} plays linked to this matchup</p>
                  <Link href={`/play-builder?matchup=${id}`} className="btn-secondary btn-sm">
                    <PenTool size={13} /> Open Play Builder
                  </Link>
                </div>
                {plays.length === 0 ? (
                  <div className="card text-center py-10 text-slate-400 text-sm">
                    No plays linked yet. Open the Play Builder and link plays to this matchup.
                  </div>
                ) : (
                  <div className="card p-0 divide-y divide-slate-50">
                    {(plays as Array<{ id: string; name: string; category: string; tags?: string[] }>).map(p => (
                      <div key={p.id} className="flex items-center gap-3 px-4 py-3">
                        <PenTool size={14} className="text-slate-400 flex-shrink-0" />
                        <div className="flex-1">
                          <p className="text-sm font-medium text-slate-700">{p.name}</p>
                          <div className="flex gap-1 mt-0.5">
                            {(p.tags ?? []).map((t: string) => (
                              <span key={t} className="text-[9px] bg-slate-100 text-slate-500 px-1.5 rounded">{t}</span>
                            ))}
                          </div>
                        </div>
                        <Link href={`/play-builder?play=${p.id}`} className="text-primary-500 hover:text-primary-700">
                          <ChevronRight size={16} />
                        </Link>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {activeTab === "tracker" && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-slate-700">Last 10 events</p>
                  <Link href={`/game-tracker?matchup=${id}`} className="btn-primary btn-sm">
                    <Activity size={13} /> Open Full Tracker
                  </Link>
                </div>
                {(recentEvents as Array<{ id: string; event_type: string; team: number; points: number; created_at: string }>).length === 0 ? (
                  <div className="card text-center py-10 text-slate-400 text-sm">No events yet.</div>
                ) : (
                  <div className="card p-0 divide-y divide-slate-50">
                    {(recentEvents as Array<{ id: string; event_type: string; team: number; points: number; created_at: string }>).map(ev => (
                      <div key={ev.id} className="flex items-center gap-3 px-4 py-3">
                        <div className={clsx("h-6 w-6 rounded-full text-white text-[10px] font-bold flex items-center justify-center flex-shrink-0",
                          ev.team === 1 ? "bg-blue-500" : "bg-violet-500")}>T{ev.team}</div>
                        <p className="text-xs font-medium text-slate-700 flex-1">{ev.event_type.replace(/_/g, " ")}</p>
                        {ev.points > 0 && <span className="text-xs font-bold text-green-600">+{ev.points}</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {activeTab === "notes" && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Game Plan Notes</p>
                  {savingNotes && <span className="text-xs text-slate-400">Saving…</span>}
                </div>
                <textarea
                  className="input w-full min-h-[300px] resize-y text-sm"
                  placeholder="Write your game plan, adjustments, key observations…"
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                />
              </div>
            )}

            {(activeTab === "scouting") && (
              <div className="card text-center py-10">
                <BookOpen size={28} className="text-slate-200 mx-auto mb-2" />
                <p className="text-slate-400 text-sm mb-3">View full scouting report</p>
                <Link href={`/scouting?matchup=${id}`} className="btn-primary btn-sm">
                  Open Scouting <ChevronRight size={13} />
                </Link>
              </div>
            )}

            {activeTab === "simulation" && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-slate-700">Monte Carlo simulation</p>
                  <button
                    type="button"
                    onClick={handleRunSimulation}
                    disabled={simRunning}
                    className="btn-primary btn-sm"
                  >
                    {simRunning ? <Loader2 size={13} className="animate-spin" /> : <Target size={13} />}
                    Run Simulation
                  </button>
                </div>

                {simulation ? (
                  <>
                    <div className="grid sm:grid-cols-3 gap-3">
                      <div className="card text-center">
                        <p className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">Win probability</p>
                        <p className="text-2xl font-bold text-slate-900">
                          {Math.round((simulation.win_pct_own ?? 0) * 100)}%
                        </p>
                      </div>
                      <div className="card text-center">
                        <p className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">Projected (us)</p>
                        <p className="text-2xl font-bold text-slate-900">
                          {(simulation.avg_score_own ?? 0).toFixed(1)}
                        </p>
                      </div>
                      <div className="card text-center">
                        <p className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">Projected (opp)</p>
                        <p className="text-2xl font-bold text-slate-900">
                          {(simulation.avg_score_opp ?? 0).toFixed(1)}
                        </p>
                      </div>
                    </div>

                    <div className="card">
                      <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">Keys to Victory</p>
                      {keys.length === 0 ? (
                        <p className="text-sm text-slate-400">No keys generated yet.</p>
                      ) : (
                        <ul className="space-y-2">
                          {keys.map((key) => (
                            <li key={key.id} className="flex items-start gap-3 p-3 rounded-xl border border-slate-100">
                              <button
                                type="button"
                                onClick={() => toggleKeyPriority(key)}
                                className={clsx(
                                  "mt-0.5 h-5 w-5 rounded border flex-shrink-0 flex items-center justify-center",
                                  key.is_priority ? "bg-indigo-600 border-indigo-600 text-white" : "border-slate-300 bg-white",
                                )}
                                title={key.is_priority ? "Remove priority" : "Mark as priority"}
                              >
                                {key.is_priority && <CheckCircle2 size={12} />}
                              </button>
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-slate-800">{key.title}</p>
                                {key.description && (
                                  <p className="text-xs text-slate-500 mt-0.5">{key.description}</p>
                                )}
                              </div>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="card text-center py-10">
                    <Target size={28} className="text-slate-200 mx-auto mb-2" />
                    <p className="text-slate-400 text-sm">No simulation yet. Run one to see projected scores and keys.</p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right sidebar */}
          <div className="space-y-4">
            {/* Win prob ring */}
            {prepStatus?.win_probability_us != null && (
              <div className="card text-center">
                <WinRing pct={winPct} />
                <p className="text-xs text-slate-400 mt-2">
                  {coachMode ? `${Math.round(winPct / 10)} wins in 10` : `${winPct}% win probability`}
                </p>
                <Link href={`/game-day?matchup=${id}`} className="text-xs text-primary-600 hover:text-primary-700 mt-1 block">
                  Run simulation →
                </Link>
              </div>
            )}

            {/* Top 3 Keys mini */}
            {priorityKeys.length > 0 && (
              <div className="card">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">Top Priorities</p>
                {priorityKeys.map((key, i) => (
                  <div key={key.id} className="flex items-start gap-2 mb-2">
                    <span className="h-5 w-5 rounded-full bg-indigo-600 text-white flex items-center justify-center text-[10px] font-bold flex-shrink-0 mt-0.5">{i+1}</span>
                    <p className="text-xs font-medium text-slate-700 leading-snug">{key.title}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Heatmap link */}
            <Link href={`/game-tracker/${id}/event-heatmap`}
              className="card flex items-center gap-2 text-sm font-medium text-primary-600 hover:text-primary-700 hover:bg-primary-50 transition-colors">
              <TrendingUp size={16} /> View Event Heatmap →
            </Link>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

export default function MatchupWorkspacePage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center py-20"><Loader2 size={24} className="animate-spin text-slate-400" /></div>}>
      <MatchupWorkspaceContent />
    </Suspense>
  );
}
