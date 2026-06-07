"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { listGames, createGame, listSeasons } from "@/lib/api";
import {
  PlusCircle,
  MapPin,
  Calendar,
  ChevronRight,
  Video,
  X,
  AlertCircle,
} from "lucide-react";
import { clsx } from "clsx";

interface Game {
  id: string;
  game_date: string | null;
  location: string | null;
  court_level: string;
  is_half_court: boolean;
  home_score: number | null;
  away_score: number | null;
}

interface Season {
  id: string;
  name: string;
  year: number;
}

const COURT_LEVELS = ["nba", "fiba_juvenil", "primaria", "mini_basket"];

const COURT_LEVEL_LABELS: Record<string, string> = {
  nba: "NBA",
  fiba_juvenil: "FIBA Juvenil",
  primaria: "Primaria",
  mini_basket: "Mini Basket",
};

const COURT_LEVEL_COLORS: Record<string, string> = {
  nba: "badge-blue",
  fiba_juvenil: "badge-violet",
  primaria: "badge-green",
  mini_basket: "badge-yellow",
};

export default function GamesPage() {
  const router = useRouter();
  const [games, setGames] = useState<Game[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [seasons, setSeasons] = useState<Season[]>([]);
  const [formData, setFormData] = useState({
    season_id: "",
    location: "",
    game_date: "",
    court_level: "primaria",
    is_half_court: false,
    home_team1_jersey: "white shirt",
    away_team2_jersey: "dark blue shirt",
  });
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    listGames()
      .then((d) => { setGames(d.items); setTotal(d.total); })
      .catch(() => router.replace("/login"))
      .finally(() => setLoading(false));
    listSeasons()
      .then((d) => {
        const items: Season[] = d.items ?? d;
        setSeasons(items);
        if (items.length > 0) {
          setFormData((prev) => ({ ...prev, season_id: items[0].id }));
        }
      })
      .catch(() => null);
  }, [router]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!formData.season_id) {
      setFormError("Please select a season. Create one in Admin if none exist.");
      return;
    }
    setCreating(true);
    try {
      const game = await createGame({
        season_id: formData.season_id,
        location: formData.location || null,
        game_date: formData.game_date || null,
        court_level: formData.court_level,
        is_half_court: formData.is_half_court,
        home_team1_jersey: formData.home_team1_jersey,
        away_team2_jersey: formData.away_team2_jersey,
      });
      setGames((prev) => [game, ...prev]);
      setTotal((t) => t + 1);
      setShowForm(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create game";
      setFormError(msg);
    } finally {
      setCreating(false);
    }
  }

  return (
    <AppShell
      title="Games & Video"
      subtitle={`${total} game${total !== 1 ? "s" : ""} recorded`}
      actions={
        <button className="btn-primary btn-sm" onClick={() => setShowForm(true)}>
          <PlusCircle size={15} />
          New Game
        </button>
      }
    >
      {/* New Game Form */}
      {showForm && (
        <div className="mb-6 card animate-fade-in">
          <div className="flex items-center justify-between mb-5">
            <h2 className="font-display text-lg font-bold text-slate-900">New Game</h2>
            <button onClick={() => { setShowForm(false); setFormError(null); }} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors">
              <X size={18} />
            </button>
          </div>
          <form onSubmit={handleCreate} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="label">Season *</label>
              {seasons.length === 0 ? (
                <p className="text-sm text-warning-600 flex items-center gap-1.5">
                  <AlertCircle size={14} />
                  No seasons found.{" "}
                  <Link href="/admin" className="underline font-medium">Create one in Admin</Link>.
                </p>
              ) : (
                <select
                  className="input"
                  value={formData.season_id}
                  onChange={(e) => setFormData({ ...formData, season_id: e.target.value })}
                  required
                >
                  {seasons.map((s) => (
                    <option key={s.id} value={s.id}>{s.name} ({s.year})</option>
                  ))}
                </select>
              )}
            </div>
            <div>
              <label className="label">Location</label>
              <input className="input" placeholder="Gym name or school" value={formData.location}
                onChange={(e) => setFormData({ ...formData, location: e.target.value })} />
            </div>
            <div>
              <label className="label">Game Date</label>
              <input type="date" className="input" value={formData.game_date}
                onChange={(e) => setFormData({ ...formData, game_date: e.target.value })} />
            </div>
            <div>
              <label className="label">Court Level</label>
              <select className="input" value={formData.court_level}
                onChange={(e) => setFormData({ ...formData, court_level: e.target.value })}>
                {COURT_LEVELS.map((l) => (
                  <option key={l} value={l}>{COURT_LEVEL_LABELS[l] ?? l}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Team 1 Jersey</label>
              <input className="input" placeholder="e.g. white shirt" value={formData.home_team1_jersey}
                onChange={(e) => setFormData({ ...formData, home_team1_jersey: e.target.value })} />
            </div>
            <div>
              <label className="label">Team 2 Jersey</label>
              <input className="input" placeholder="e.g. dark blue shirt" value={formData.away_team2_jersey}
                onChange={(e) => setFormData({ ...formData, away_team2_jersey: e.target.value })} />
            </div>
            <div className="flex items-center gap-2.5 sm:col-span-2">
              <input type="checkbox" id="halfcourt" className="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
                checked={formData.is_half_court}
                onChange={(e) => setFormData({ ...formData, is_half_court: e.target.checked })} />
              <label htmlFor="halfcourt" className="text-sm font-medium text-slate-700">Half-court game</label>
            </div>
            {formError && (
              <div className="sm:col-span-2 flex items-center gap-2 rounded-lg bg-danger-50 px-4 py-2.5 text-sm text-danger-600 ring-1 ring-danger-100">
                <AlertCircle size={15} />
                {formError}
              </div>
            )}
            <div className="flex gap-3 sm:col-span-2">
              <button type="submit" className="btn-primary" disabled={creating}>
                {creating ? "Creating…" : "Create Game"}
              </button>
              <button type="button" className="btn-secondary"
                onClick={() => { setShowForm(false); setFormError(null); }}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Games grid */}
      {loading ? (
        <div className="flex items-center justify-center py-24 text-slate-400">
          <div className="flex flex-col items-center gap-3">
            <div className="h-8 w-8 rounded-full border-2 border-primary-200 border-t-primary-600 animate-spin" />
            <p className="text-sm">Loading games…</p>
          </div>
        </div>
      ) : games.length === 0 ? (
        <div className="card text-center py-20">
          <div className="mx-auto mb-4 h-14 w-14 rounded-2xl bg-primary-50 flex items-center justify-center">
            <Video size={24} className="text-primary-600" />
          </div>
          <p className="font-display font-bold text-slate-900 mb-1">No games yet</p>
          <p className="text-sm text-slate-500 mb-5">Create your first game to start analyzing</p>
          <button className="btn-primary inline-flex" onClick={() => setShowForm(true)}>
            <PlusCircle size={15} />
            New Game
          </button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {games.map((g) => (
            <Link key={g.id} href={`/games/${g.id}`} className="card-hover block">
              {/* Card header */}
              <div className="flex items-start justify-between gap-2 mb-3">
                <div className="flex flex-wrap gap-1.5">
                  <span className={clsx("badge", COURT_LEVEL_COLORS[g.court_level] ?? "badge-gray")}>
                    {COURT_LEVEL_LABELS[g.court_level] ?? g.court_level}
                  </span>
                  {g.is_half_court && (
                    <span className="badge badge-yellow">Half-court</span>
                  )}
                </div>
                <ChevronRight size={16} className="text-slate-300 flex-shrink-0 mt-0.5" />
              </div>

              {/* Score */}
              {(g.home_score != null || g.away_score != null) && (
                <p className="text-2xl font-bold text-slate-900 mb-2">
                  {g.home_score ?? "–"} <span className="text-slate-300">vs</span> {g.away_score ?? "–"}
                </p>
              )}

              {/* Details */}
              <div className="space-y-1.5">
                {g.location && (
                  <div className="flex items-center gap-1.5 text-sm text-slate-500">
                    <MapPin size={13} className="flex-shrink-0" />
                    <span className="truncate">{g.location}</span>
                  </div>
                )}
                {g.game_date && (
                  <div className="flex items-center gap-1.5 text-sm text-slate-500">
                    <Calendar size={13} className="flex-shrink-0" />
                    <span>{new Date(g.game_date).toLocaleDateString()}</span>
                  </div>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </AppShell>
  );
}
