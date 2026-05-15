"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Navbar from "@/components/Navbar";
import { listGames, createGame } from "@/lib/api";

interface Game {
  id: string;
  game_date: string | null;
  location: string | null;
  court_level: string;
  is_half_court: boolean;
  home_score: number | null;
  away_score: number | null;
}

const COURT_LEVELS = ["nba", "fiba_juvenil", "primaria", "mini_basket"];

export default function GamesPage() {
  const router = useRouter();
  const [games, setGames] = useState<Game[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    season_id: "",
    location: "",
    game_date: "",
    court_level: "primaria",
    is_half_court: false,
    home_team1_jersey: "white shirt",
    away_team2_jersey: "dark blue shirt",
  });

  useEffect(() => {
    listGames()
      .then((d) => { setGames(d.items); setTotal(d.total); })
      .catch(() => router.replace("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
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
    setShowForm(false);
  }

  return (
    <>
      <Navbar />
      <main className="mx-auto max-w-7xl px-4 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Games</h1>
            <p className="text-sm text-gray-500 mt-0.5">{total} total</p>
          </div>
          <button className="btn-primary" onClick={() => setShowForm(true)}>
            + New Game
          </button>
        </div>

        {/* Create form */}
        {showForm && (
          <div className="card mb-6">
            <h2 className="text-lg font-semibold mb-4">New Game</h2>
            <form onSubmit={handleCreate} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="label">Season ID (UUID)</label>
                <input className="input" required value={formData.season_id}
                  onChange={(e) => setFormData({ ...formData, season_id: e.target.value })} />
              </div>
              <div>
                <label className="label">Location</label>
                <input className="input" value={formData.location}
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
                  {COURT_LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </div>
              <div>
                <label className="label">Team 1 Jersey (zero-shot text)</label>
                <input className="input" value={formData.home_team1_jersey}
                  onChange={(e) => setFormData({ ...formData, home_team1_jersey: e.target.value })} />
              </div>
              <div>
                <label className="label">Team 2 Jersey (zero-shot text)</label>
                <input className="input" value={formData.away_team2_jersey}
                  onChange={(e) => setFormData({ ...formData, away_team2_jersey: e.target.value })} />
              </div>
              <div className="flex items-center gap-2 sm:col-span-2">
                <input type="checkbox" id="halfcourt" checked={formData.is_half_court}
                  onChange={(e) => setFormData({ ...formData, is_half_court: e.target.checked })} />
                <label htmlFor="halfcourt" className="text-sm font-medium text-gray-700">
                  Half-court game
                </label>
              </div>
              <div className="flex gap-3 sm:col-span-2">
                <button type="submit" className="btn-primary">Create</button>
                <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>Cancel</button>
              </div>
            </form>
          </div>
        )}

        {/* Games list */}
        {loading ? (
          <div className="text-center py-20 text-gray-400">Loading…</div>
        ) : games.length === 0 ? (
          <div className="text-center py-20 text-gray-400">No games yet. Create one above!</div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {games.map((g) => (
              <Link key={g.id} href={`/games/${g.id}`} className="card hover:shadow-md transition-shadow block">
                <div className="flex items-start justify-between">
                  <div>
                    <span className="inline-block rounded-full bg-primary-50 px-2.5 py-0.5 text-xs font-semibold text-primary-700">
                      {g.court_level}
                    </span>
                    {g.is_half_court && (
                      <span className="ml-1.5 inline-block rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-700">
                        Half-court
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-gray-400">{g.game_date ?? "No date"}</span>
                </div>
                <p className="mt-3 text-sm font-medium text-gray-700">{g.location ?? "No location"}</p>
                {(g.home_score != null || g.away_score != null) && (
                  <p className="mt-1 text-lg font-bold">
                    {g.home_score ?? "–"} – {g.away_score ?? "–"}
                  </p>
                )}
                <p className="mt-3 text-xs text-gray-400 truncate font-mono">{g.id}</p>
              </Link>
            ))}
          </div>
        )}
      </main>
    </>
  );
}
