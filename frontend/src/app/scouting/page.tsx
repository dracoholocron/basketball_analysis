"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import AppShell from "@/components/layout/AppShell";
import {
  listMatchups, createMatchup, listTeams,
  getScoutingReport, generateScoutingReport, updateScoutingNotes,
} from "@/lib/api";
import {
  Search, PlusCircle, Loader2, Sparkles, ChevronRight,
  AlertCircle, RefreshCw, CheckCircle2, StickyNote, X,
  TrendingDown, TrendingUp, Trophy, Brain, Video, Zap,
} from "lucide-react";
import { getVideoInsights } from "@/lib/api";
import { clsx } from "clsx";
import { useSelfScout } from "@/lib/selfScout";

interface Team { id: string; name: string; }
interface Matchup { id: string; name: string; status: string; own_team_id?: string; opponent_team_id?: string; game_date?: string; }
interface ScoutingReport {
  id: string;
  team_identity: string;
  strengths: string[];
  weaknesses: string[];
  mvp_players: { name: string; jersey: string; summary: string }[];
  game_keys_offensive: string[];
  game_keys_defensive: string[];
  coach_notes: string;
  generated_at: string;
}

interface VideoInsightPlayer {
  player_name: string;
  jersey_number?: string;
  avg_pts: number;
  avg_ast: number;
  avg_reb: number;
  avg_stl: number;
  avg_blk: number;
  fg_pct: number;
  games: number;
}

interface VideoInsights {
  insights: { team_role: string; team_id: string; players: VideoInsightPlayer[] }[];
  note: string;
}

function ScoutingPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { selfScout } = useSelfScout();
  const [matchups, setMatchups] = useState<Matchup[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [selectedMatchup, setSelectedMatchup] = useState<string | null>(null);
  const [report, setReport] = useState<ScoutingReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [videoInsights, setVideoInsights] = useState<VideoInsights | null>(null);
  const [coachNotes, setCoachNotes] = useState("");
  const [notesSaved, setNotesSaved] = useState(false);
  const [form, setForm] = useState({ name: "", own_team_id: "", opponent_team_id: "" });

  const loadMatchups = useCallback(async () => {
    try {
      const data = await listMatchups();
      setMatchups(data);
    } catch {
      router.replace("/login");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    loadMatchups();
    listTeams().then((d) => setTeams(d.items ?? d)).catch(() => null);
  }, [loadMatchups]);

  useEffect(() => {
    const matchupId = searchParams.get("matchup");
    if (matchupId) loadReport(matchupId);
  }, [searchParams]);

  async function loadReport(matchupId: string) {
    setSelectedMatchup(matchupId);
    setReport(null);
    setVideoInsights(null);
    try {
      const r = await getScoutingReport(matchupId);
      setReport(r);
      setCoachNotes(r.coach_notes ?? "");
    } catch {
      // No report yet
    }
    // Load video insights independently
    getVideoInsights(matchupId).then(setVideoInsights).catch(() => null);
  }

  async function handleGenerate() {
    if (!selectedMatchup) return;
    setGenerating(true);
    try {
      const r = await generateScoutingReport(selectedMatchup);
      setReport(r);
      setCoachNotes(r.coach_notes ?? "");
    } catch (err) {
      console.error(err);
    } finally {
      setGenerating(false);
    }
  }

  async function handleSaveNotes() {
    if (!report) return;
    try {
      await updateScoutingNotes(report.id, coachNotes);
      setNotesSaved(true);
      setTimeout(() => setNotesSaved(false), 2000);
    } catch (err) {
      console.error(err);
    }
  }

  async function handleCreateMatchup(e: React.FormEvent) {
    e.preventDefault();
    try {
      const m = await createMatchup(form);
      setMatchups((prev) => [m, ...prev]);
      setShowForm(false);
      setForm({ name: "", own_team_id: "", opponent_team_id: "" });
      loadReport(m.id);
    } catch (err) {
      console.error(err);
    }
  }

  const selectedMatchupData = matchups.find((m) => m.id === selectedMatchup);

  // Self-Scout: swap own/opponent perspective for display labels
  const perspectiveLabel = selfScout ? "Self-Scout (Your Team as Opponent)" : "Opponent Analysis";
  const targetTeamId = selfScout
    ? selectedMatchupData?.own_team_id
    : selectedMatchupData?.opponent_team_id;
  const targetTeamName = teams.find(t => t.id === targetTeamId)?.name ?? "Opponent";

  return (
    <AppShell
      title={selfScout ? "Self-Scout" : "Scouting"}
      subtitle={perspectiveLabel}
      actions={
        <button className="btn-violet btn-sm" onClick={() => setShowForm(true)}>
          <PlusCircle size={15} />
          New Matchup
        </button>
      }
    >
      <div className="flex gap-6 max-w-6xl mx-auto">
        {/* Matchup list */}
        <div className="w-72 flex-shrink-0">
          <div className="card p-0 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-50">
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Matchups</p>
            </div>

            {showForm && (
              <div className="p-4 border-b border-slate-50 bg-slate-50 animate-fade-in">
                <form onSubmit={handleCreateMatchup} className="space-y-3">
                  <div>
                    <label className="label text-xs">Name</label>
                    <input className="input text-sm" required placeholder="vs. Eagles — Feb 2026" value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })} />
                  </div>
                  <div>
                    <label className="label text-xs">Our Team</label>
                    <select className="input text-sm" value={form.own_team_id}
                      onChange={(e) => setForm({ ...form, own_team_id: e.target.value })}>
                      <option value="">— select —</option>
                      {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="label text-xs">Opponent</label>
                    <select className="input text-sm" value={form.opponent_team_id}
                      onChange={(e) => setForm({ ...form, opponent_team_id: e.target.value })}>
                      <option value="">— select —</option>
                      {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </select>
                  </div>
                  <div className="flex gap-2">
                    <button type="submit" className="btn-violet btn-sm flex-1">Create</button>
                    <button type="button" className="btn-ghost btn-sm" onClick={() => setShowForm(false)}>
                      <X size={14} />
                    </button>
                  </div>
                </form>
              </div>
            )}

            {loading ? (
              <div className="flex items-center justify-center py-10">
                <Loader2 size={20} className="animate-spin text-slate-400" />
              </div>
            ) : matchups.length === 0 ? (
              <div className="text-center py-10 px-4">
                <Search size={24} className="mx-auto mb-2 text-slate-300" />
                <p className="text-xs text-slate-400">No matchups yet</p>
                <button className="mt-3 text-xs text-violet-600 hover:text-violet-700 font-medium" onClick={() => setShowForm(true)}>
                  + New Matchup
                </button>
              </div>
            ) : (
              <div className="divide-y divide-slate-50">
                {matchups.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => loadReport(m.id)}
                    className={clsx(
                      "w-full text-left px-4 py-3 flex items-center gap-3 hover:bg-slate-50 transition-colors",
                      selectedMatchup === m.id && "bg-violet-50"
                    )}
                  >
                    <div className="flex-1 min-w-0">
                      <p className={clsx("text-sm font-medium truncate", selectedMatchup === m.id ? "text-violet-700" : "text-slate-700")}>
                        {m.name}
                      </p>
                      <p className="text-xs text-slate-400 mt-0.5">{m.game_date ?? "No date"}</p>
                    </div>
                    <span className={clsx(
                      "badge flex-shrink-0",
                      m.status === "scouted" ? "badge-green" : "badge-gray"
                    )}>
                      {m.status}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Report panel */}
        <div className="flex-1 min-w-0">
          {!selectedMatchup ? (
            <div className="card text-center py-20">
              <Brain size={32} className="mx-auto mb-4 text-violet-300" />
              <p className="font-display font-bold text-slate-800 mb-1">Select a Matchup</p>
              <p className="text-sm text-slate-500">Choose a matchup from the left to view or generate a scouting report.</p>
            </div>
          ) : report ? (
            <div className="space-y-5 animate-fade-in">
              {/* Header */}
              <div className="card flex items-start justify-between gap-4">
                <div>
                  <h2 className="font-display text-lg font-bold text-slate-900">{selectedMatchupData?.name}</h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Generated {new Date(report.generated_at).toLocaleString()}
                  </p>
                </div>
                <button onClick={handleGenerate} disabled={generating} className="btn-violet btn-sm flex-shrink-0">
                  {generating ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                  Regenerate
                </button>
              </div>

              {/* Self-Scout perspective banner */}
              {selfScout && (
                <div className="flex items-center gap-3 rounded-xl bg-violet-50 border border-violet-200 px-4 py-3">
                  <Brain size={16} className="text-violet-600 flex-shrink-0" />
                  <div>
                    <p className="text-sm font-semibold text-violet-900">Self-Scout Mode — Viewing as {targetTeamName}</p>
                    <p className="text-xs text-violet-600 mt-0.5">This is how opponents would scout your team. Strengths are their assets to contain; weaknesses are areas to improve.</p>
                  </div>
                </div>
              )}

              {/* Team Identity */}
              <div className="card">
                <div className="flex items-center gap-2 mb-3">
                  <Trophy size={16} className="text-warning-500" />
                  <h3 className="font-semibold text-slate-900">
                    {selfScout ? `${targetTeamName} — Playing Style` : "Opponent Identity & Playing Style"}
                  </h3>
                </div>
                <p className="text-sm text-slate-600 leading-relaxed">{report.team_identity}</p>
              </div>

              {/* Strengths & Weaknesses */}
              <div className="grid sm:grid-cols-2 gap-4">
                <div className="card border-l-4 border-danger-400">
                  <div className="flex items-center gap-2 mb-3">
                    <TrendingUp size={16} className="text-danger-500" />
                    <h3 className="font-semibold text-slate-900">{selfScout ? "Your Strengths" : "Strengths to Stop"}</h3>
                  </div>
                  <ul className="space-y-2">
                    {report.strengths?.map((s, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm">
                        <span className="h-5 w-5 rounded-full bg-danger-100 text-danger-600 flex items-center justify-center flex-shrink-0 text-[10px] font-bold mt-0.5">{i + 1}</span>
                        <span className="text-slate-700">{s}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="card border-l-4 border-success-400">
                  <div className="flex items-center gap-2 mb-3">
                    <TrendingDown size={16} className="text-success-500" />
                    <h3 className="font-semibold text-slate-900">{selfScout ? "Areas to Improve" : "Weaknesses to Exploit"}</h3>
                  </div>
                  <ul className="space-y-2">
                    {report.weaknesses?.map((w, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm">
                        <span className="h-5 w-5 rounded-full bg-success-100 text-success-600 flex items-center justify-center flex-shrink-0 text-[10px] font-bold mt-0.5">{i + 1}</span>
                        <span className="text-slate-700">{w}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Game Keys */}
              <div className="grid sm:grid-cols-2 gap-4">
                <div className="card">
                  <h3 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
                    <span className="h-5 w-5 rounded bg-primary-100 text-primary-700 flex items-center justify-center text-[10px] font-bold">O</span>
                    Offensive Keys
                  </h3>
                  <ul className="space-y-2">
                    {report.game_keys_offensive?.map((k, i) => (
                      <li key={i} className="text-sm text-slate-600 flex items-start gap-2">
                        <ChevronRight size={14} className="text-primary-400 flex-shrink-0 mt-0.5" />
                        {k}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="card">
                  <h3 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
                    <span className="h-5 w-5 rounded bg-violet-100 text-violet-700 flex items-center justify-center text-[10px] font-bold">D</span>
                    Defensive Keys
                  </h3>
                  <ul className="space-y-2">
                    {report.game_keys_defensive?.map((k, i) => (
                      <li key={i} className="text-sm text-slate-600 flex items-start gap-2">
                        <ChevronRight size={14} className="text-violet-400 flex-shrink-0 mt-0.5" />
                        {k}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* MVPs */}
              {report.mvp_players && report.mvp_players.length > 0 && (
                <div className="card">
                  <h3 className="font-semibold text-slate-900 mb-4">Top Players to Watch</h3>
                  <div className="grid sm:grid-cols-3 gap-4">
                    {report.mvp_players.map((p, i) => (
                      <div key={i} className="rounded-xl bg-slate-50 p-4 border border-slate-100">
                        <div className="flex items-center gap-2 mb-2">
                          <div className="h-8 w-8 rounded-full bg-primary-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                            {(i + 1)}
                          </div>
                          <div>
                            <p className="font-semibold text-sm text-slate-900">{p.name}</p>
                            <p className="text-xs text-slate-400">{p.jersey}</p>
                          </div>
                        </div>
                        <p className="text-xs text-slate-600 leading-relaxed">{p.summary}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Video Insights (F10) */}
              {videoInsights && videoInsights.insights.length > 0 && (
                <div className="card border-l-4 border-primary-400">
                  <div className="flex items-center gap-2 mb-4">
                    <Video size={16} className="text-primary-500" />
                    <h3 className="font-semibold text-slate-900">Video Intelligence</h3>
                    <span className="badge badge-blue ml-1">
                      <Zap size={10} /> CV Data
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mb-4">{videoInsights.note}</p>
                  {videoInsights.insights.map((insight) => (
                    <div key={insight.team_role} className="mb-4">
                      <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2 capitalize">
                        {insight.team_role === "opponent" ? "Opponent" : "Our Team"} — Box score averages
                      </p>
                      <div className="overflow-x-auto">
                        <table className="min-w-full text-xs">
                          <thead>
                            <tr className="text-left text-slate-400 border-b border-slate-100">
                              <th className="pb-1 pr-4">Player</th>
                              <th className="pb-1 pr-4">PTS</th>
                              <th className="pb-1 pr-4">AST</th>
                              <th className="pb-1 pr-4">REB</th>
                              <th className="pb-1 pr-4">STL</th>
                              <th className="pb-1">FG%</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-50">
                            {insight.players.slice(0, 5).map((p, i) => (
                              <tr key={i}>
                                <td className="py-1.5 pr-4 font-medium text-slate-700">{p.jersey_number ? `#${p.jersey_number} ` : ""}{p.player_name}</td>
                                <td className="py-1.5 pr-4 text-slate-600">{(p?.avg_pts ?? 0).toFixed(1)}</td>
                                <td className="py-1.5 pr-4 text-slate-600">{(p?.avg_ast ?? 0).toFixed(1)}</td>
                                <td className="py-1.5 pr-4 text-slate-600">{(p?.avg_reb ?? 0).toFixed(1)}</td>
                                <td className="py-1.5 pr-4 text-slate-600">{(p?.avg_stl ?? 0).toFixed(1)}</td>
                                <td className="py-1.5 text-slate-600">{((p?.fg_pct ?? 0) * 100).toFixed(1)}%</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Coach Notes */}
              <div className="card">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-slate-900 flex items-center gap-2">
                    <StickyNote size={16} className="text-warning-500" />
                    Coach Notes
                  </h3>
                  <div className="flex items-center gap-2">
                    {notesSaved && (
                      <span className="flex items-center gap-1 text-xs text-success-600">
                        <CheckCircle2 size={13} /> Saved
                      </span>
                    )}
                    <button onClick={handleSaveNotes} className="btn-secondary btn-sm">
                      Save Notes
                    </button>
                  </div>
                </div>
                <textarea
                  className="input min-h-[120px] resize-none"
                  placeholder="Add your own notes, adjustments, or observations..."
                  value={coachNotes}
                  onChange={(e) => setCoachNotes(e.target.value)}
                />
              </div>
            </div>
          ) : (
            <div className="card text-center py-16">
              {generating ? (
                <div className="flex flex-col items-center gap-4">
                  <div className="h-12 w-12 rounded-2xl bg-violet-50 flex items-center justify-center">
                    <Loader2 size={24} className="animate-spin text-violet-600" />
                  </div>
                  <div>
                    <p className="font-display font-bold text-slate-900 mb-1">Generating Report…</p>
                    <p className="text-sm text-slate-500">AI is analyzing the matchup. This may take a few seconds.</p>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-4">
                  <div className="h-12 w-12 rounded-2xl bg-violet-50 flex items-center justify-center">
                    <Sparkles size={24} className="text-violet-600" />
                  </div>
                  <div>
                    <p className="font-display font-bold text-slate-900 mb-1">No Report Yet</p>
                    <p className="text-sm text-slate-500 mb-5">Generate an AI scouting report for {selectedMatchupData?.name}</p>
                    <button onClick={handleGenerate} className="btn-violet">
                      <Sparkles size={15} />
                      Generate Scouting Report
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}

export default function ScoutingPage() {
  return (
    <Suspense fallback={
      <AppShell title="Scouting">
        <div className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-slate-400" />
        </div>
      </AppShell>
    }>
      <ScoutingPageContent />
    </Suspense>
  );
}
