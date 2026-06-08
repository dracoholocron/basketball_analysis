"use client";

import { useState, useEffect, useRef } from "react";
import AppShell from "@/components/layout/AppShell";
import {
  listSeasons, listTeams, listGames, listBoxScores, createBoxScore, importBoxScoresCsv, getTeamAverages,
} from "@/lib/api";
import { Upload, PlusCircle, Loader2, AlertCircle, CheckCircle2, ChevronDown, ChevronUp, BarChart2 } from "lucide-react";
import { clsx } from "clsx";

interface Season { id: string; name: string; year?: string; }
interface Team { id: string; name: string; }
interface Game { id: string; home_team_id?: string; away_team_id?: string; season_id?: string; court_level?: string; }
interface BoxScore { id: string; game_id: string; team_id: string; pts: number; fgm: number; fga: number; fg3m: number; fg3a: number; ftm: number; fta: number; oreb: number; dreb: number; ast: number; stl: number; blk: number; tov: number; pf: number; }
interface TeamAverages { games_played: number; avg_pts: number; fg_pct: number; fg3_pct: number; ft_pct: number; avg_reb: number; avg_ast: number; avg_stl: number; avg_blk: number; avg_tov: number; }

const STAT_FIELDS = ["pts","fgm","fga","fg3m","fg3a","ftm","fta","oreb","dreb","ast","stl","blk","tov","pf"] as const;
type StatField = typeof STAT_FIELDS[number];

const PLAYER_FIELDS: StatField[] = ["pts","fgm","fga","fg3m","fg3a","ftm","fta","oreb","dreb","ast","stl","blk","tov","pf"];

const emptyStats = () => Object.fromEntries(STAT_FIELDS.map(f => [f, 0])) as Record<StatField, number>;

export default function BoxScoresAdminPage() {
  const [seasons, setSeasons] = useState<Season[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [boxScores, setBoxScores] = useState<BoxScore[]>([]);
  const [averages, setAverages] = useState<TeamAverages | null>(null);

  const [selectedSeason, setSelectedSeason] = useState("");
  const [selectedTeam, setSelectedTeam] = useState("");
  const [selectedGame, setSelectedGame] = useState("");

  const [teamStats, setTeamStats] = useState<Record<StatField, number>>(emptyStats());
  const [players, setPlayers] = useState([
    { player_name: "", jersey_number: "", minutes_played: "", ...emptyStats() },
  ]);

  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [showManual, setShowManual] = useState(false);
  const [showAverages, setShowAverages] = useState(false);

  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    Promise.all([listSeasons(), listTeams()]).then(([s, t]) => {
      setSeasons(s);
      setTeams(t);
    });
  }, []);

  useEffect(() => {
    if (!selectedSeason) return;
    listGames().then(gs => setGames(gs.filter((g: Game) => g.season_id === selectedSeason)));
  }, [selectedSeason]);

  useEffect(() => {
    if (!selectedGame || !selectedTeam) return;
    listBoxScores({ game_id: selectedGame, team_id: selectedTeam }).then(setBoxScores);
  }, [selectedGame, selectedTeam]);

  useEffect(() => {
    if (!selectedTeam || !selectedSeason) return;
    getTeamAverages(selectedTeam, selectedSeason).then(setAverages).catch(() => setAverages(null));
  }, [selectedTeam, selectedSeason]);

  function addPlayerRow() {
    setPlayers(p => [...p, { player_name: "", jersey_number: "", minutes_played: "", ...emptyStats() }]);
  }

  function updatePlayer(idx: number, field: string, value: string | number) {
    setPlayers(p => p.map((row, i) => i === idx ? { ...row, [field]: value } : row));
  }

  async function handleManualSubmit() {
    if (!selectedGame || !selectedTeam) {
      setMsg({ type: "err", text: "Select a game and team first." });
      return;
    }
    setLoading(true);
    setMsg(null);
    try {
      await createBoxScore({
        game_id: selectedGame,
        team_id: selectedTeam,
        ...teamStats,
        players: players
          .filter(p => p.player_name.trim())
          .map(p => ({
            player_name: p.player_name,
            jersey_number: p.jersey_number || null,
            minutes_played: p.minutes_played ? parseFloat(p.minutes_played) : null,
            pts: Number(p.pts), fgm: Number(p.fgm), fga: Number(p.fga),
            fg3m: Number(p.fg3m), fg3a: Number(p.fg3a), ftm: Number(p.ftm), fta: Number(p.fta),
            oreb: Number(p.oreb), dreb: Number(p.dreb), ast: Number(p.ast),
            stl: Number(p.stl), blk: Number(p.blk), tov: Number(p.tov), pf: Number(p.pf),
          })),
      });
      setMsg({ type: "ok", text: "Box score saved!" });
      listBoxScores({ game_id: selectedGame, team_id: selectedTeam }).then(setBoxScores);
      setTeamStats(emptyStats());
      setPlayers([{ player_name: "", jersey_number: "", minutes_played: "", ...emptyStats() }]);
    } catch {
      setMsg({ type: "err", text: "Failed to save box score." });
    } finally {
      setLoading(false);
    }
  }

  async function handleCsvImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !selectedSeason || !selectedGame || !selectedTeam) {
      setMsg({ type: "err", text: "Select season, game, and team before importing." });
      return;
    }
    setImporting(true);
    setMsg(null);
    try {
      const result = await importBoxScoresCsv(selectedGame, selectedTeam, file);
      const detail =
        result?.imported != null
          ? `${result.message ?? "CSV imported."} (${result.imported} imported, ${result.skipped ?? 0} skipped)`
          : (result?.message ?? "CSV imported!");
      setMsg({ type: "ok", text: detail });
      listBoxScores({ game_id: selectedGame, team_id: selectedTeam }).then(setBoxScores);
    } catch {
      setMsg({ type: "err", text: "CSV import failed. Check format." });
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const filteredGames = selectedSeason
    ? games.filter(g => g.season_id === selectedSeason || !g.season_id)
    : games;

  return (
    <AppShell title="Box Score Management" subtitle="Manual entry & CSV import">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* Filters */}
        <div className="card">
          <h2 className="section-title mb-4">Select Context</h2>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="label">Season</label>
              <select className="select" value={selectedSeason} onChange={e => setSelectedSeason(e.target.value)}>
                <option value="">— choose —</option>
                {seasons.map(s => <option key={s.id} value={s.id}>{s.name} {s.year ? `(${s.year})` : ""}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Team</label>
              <select className="select" value={selectedTeam} onChange={e => setSelectedTeam(e.target.value)}>
                <option value="">— choose —</option>
                {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Game</label>
              <select className="select" value={selectedGame} onChange={e => setSelectedGame(e.target.value)}>
                <option value="">— choose —</option>
                {filteredGames.map(g => <option key={g.id} value={g.id}>Game {g.id.slice(0, 8)}… {g.court_level ? `(${g.court_level})` : ""}</option>)}
              </select>
            </div>
          </div>
        </div>

        {msg && (
          <div className={clsx("flex items-center gap-2 rounded-lg px-4 py-3 text-sm", msg.type === "ok" ? "bg-success/10 text-success" : "bg-danger/10 text-danger")}>
            {msg.type === "ok" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
            {msg.text}
          </div>
        )}

        {/* CSV Import */}
        <div className="card">
          <h2 className="section-title mb-2">CSV Import</h2>
          <p className="text-xs text-slate-500 mb-4">
            One row per player. Required header: <code className="bg-slate-100 px-1 rounded">player_name</code>.
            Optional stats (default 0):{" "}
            <code className="bg-slate-100 px-1 rounded">
              jersey_number, minutes_played, pts, fgm, fga, fg3m, fg3a, ftm, fta, oreb, dreb, ast, stl, blk, tov, pf, plus_minus
            </code>
            . Headers are case-insensitive; team totals are summed from player rows.
          </p>
          <div className="flex items-center gap-3">
            <label className={clsx("btn-secondary cursor-pointer flex items-center gap-2", (!selectedSeason || !selectedGame || !selectedTeam) && "opacity-50 cursor-not-allowed")}>
              {importing ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
              {importing ? "Importing…" : "Upload CSV"}
              <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={handleCsvImport} disabled={importing || !selectedSeason || !selectedGame || !selectedTeam} />
            </label>
            <span className="text-xs text-slate-400">Select season, team & game first</span>
          </div>
        </div>

        {/* Manual Entry */}
        <div className="card">
          <button className="flex w-full items-center justify-between" onClick={() => setShowManual(v => !v)}>
            <h2 className="section-title">Manual Entry (Spreadsheet)</h2>
            {showManual ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
          </button>

          {showManual && (
            <div className="mt-4 space-y-4">
              {/* Team totals */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Team Totals</h3>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-xs">
                    <thead>
                      <tr className="text-left text-slate-400 border-b border-slate-100">
                        {STAT_FIELDS.map(f => <th key={f} className="pb-1 pr-3 uppercase">{f}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        {STAT_FIELDS.map(f => (
                          <td key={f} className="pr-2 py-1">
                            <input
                              type="number" min={0}
                              className="w-14 border border-slate-200 rounded px-1.5 py-1 text-xs text-center focus:outline-none focus:ring-1 focus:ring-primary-400"
                              value={teamStats[f]}
                              onChange={e => setTeamStats(s => ({ ...s, [f]: Number(e.target.value) }))}
                            />
                          </td>
                        ))}
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Player rows */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Player Stats</h3>
                <div className="overflow-x-auto">
                  <table className="min-w-full text-xs">
                    <thead>
                      <tr className="text-left text-slate-400 border-b border-slate-100">
                        <th className="pb-1 pr-3">Name</th>
                        <th className="pb-1 pr-3">#</th>
                        <th className="pb-1 pr-3">MIN</th>
                        {PLAYER_FIELDS.map(f => <th key={f} className="pb-1 pr-3 uppercase">{f}</th>)}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {players.map((row, i) => (
                        <tr key={i}>
                          <td className="pr-2 py-1">
                            <input className="border border-slate-200 rounded px-1.5 py-1 text-xs w-28 focus:outline-none focus:ring-1 focus:ring-primary-400" value={row.player_name} onChange={e => updatePlayer(i, "player_name", e.target.value)} placeholder="Player name" />
                          </td>
                          <td className="pr-2 py-1">
                            <input className="border border-slate-200 rounded px-1.5 py-1 text-xs w-10 focus:outline-none focus:ring-1 focus:ring-primary-400" value={row.jersey_number} onChange={e => updatePlayer(i, "jersey_number", e.target.value)} placeholder="#" />
                          </td>
                          <td className="pr-2 py-1">
                            <input type="number" className="border border-slate-200 rounded px-1.5 py-1 text-xs w-12 focus:outline-none focus:ring-1 focus:ring-primary-400" value={row.minutes_played} onChange={e => updatePlayer(i, "minutes_played", e.target.value)} placeholder="0" />
                          </td>
                          {PLAYER_FIELDS.map(f => (
                            <td key={f} className="pr-2 py-1">
                              <input type="number" min={0} className="w-12 border border-slate-200 rounded px-1.5 py-1 text-xs text-center focus:outline-none focus:ring-1 focus:ring-primary-400" value={row[f]} onChange={e => updatePlayer(i, f, Number(e.target.value))} />
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <button className="btn-secondary btn-sm mt-2 flex items-center gap-1" onClick={addPlayerRow}>
                  <PlusCircle size={14} /> Add Player Row
                </button>
              </div>

              <div className="flex justify-end">
                <button className="btn-primary flex items-center gap-2" onClick={handleManualSubmit} disabled={loading}>
                  {loading ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />}
                  Save Box Score
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Team Averages */}
        {averages && selectedTeam && (
          <div className="card">
            <button className="flex w-full items-center justify-between" onClick={() => setShowAverages(v => !v)}>
              <h2 className="section-title flex items-center gap-2"><BarChart2 size={16} /> Season Averages</h2>
              {showAverages ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
            </button>
            {showAverages && (
              <div className="mt-4 grid grid-cols-5 gap-3">
                {[
                  { label: "Games", value: averages.games_played, fmt: (v: number) => v.toString() },
                  { label: "PPG", value: averages.avg_pts, fmt: (v: number) => v.toFixed(1) },
                  { label: "FG%", value: averages.fg_pct, fmt: (v: number) => `${(v * 100).toFixed(1)}%` },
                  { label: "3P%", value: averages.fg3_pct, fmt: (v: number) => `${(v * 100).toFixed(1)}%` },
                  { label: "FT%", value: averages.ft_pct, fmt: (v: number) => `${(v * 100).toFixed(1)}%` },
                  { label: "RPG", value: averages.avg_reb, fmt: (v: number) => v.toFixed(1) },
                  { label: "APG", value: averages.avg_ast, fmt: (v: number) => v.toFixed(1) },
                  { label: "SPG", value: averages.avg_stl, fmt: (v: number) => v.toFixed(1) },
                  { label: "BPG", value: averages.avg_blk, fmt: (v: number) => v.toFixed(1) },
                  { label: "TOV", value: averages.avg_tov, fmt: (v: number) => v.toFixed(1) },
                ].map(({ label, value, fmt }) => (
                  <div key={label} className="stat-card text-center">
                    <div className="stat-value text-xl">{fmt(value)}</div>
                    <div className="stat-label">{label}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Existing box scores */}
        {boxScores.length > 0 && (
          <div className="card">
            <h2 className="section-title mb-3">Recorded Box Scores for this Game</h2>
            <div className="overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="text-left text-slate-400 border-b border-slate-100">
                    <th className="pb-1 pr-4">ID</th>
                    {STAT_FIELDS.map(f => <th key={f} className="pb-1 pr-3 uppercase">{f}</th>)}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {boxScores.map(bs => (
                    <tr key={bs.id}>
                      <td className="py-1.5 pr-4 text-slate-400 font-mono">{bs.id.slice(0, 8)}…</td>
                      {STAT_FIELDS.map(f => <td key={f} className="py-1.5 pr-3 font-medium">{bs[f as StatField]}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
