"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Navbar from "@/components/Navbar";
import { listGames, createGame, listSeasons } from "@/lib/api";

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

        {showForm && (
          <div className="card mb-6">
            <h2 className="text-lg font-semibold mb-4">New Game</h2>
            <form onSubmit={handleCreate} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="label">Season</label>
                {seasons.length === 0 ? (
                  <p className="text-sm text-amber-600">
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
                      <option key={s.id} value={s.id}>
                        {s.name} ({s.year})
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <div>
                <label className="label">Location</label>
                <input
                  className="input"
                  placeholder="Gym name or school"
                  value={formData.location}
                  onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                />
              </div>
              <div>
                <label className="label">Game Date</label>
                <input
                  type="date"
                  className="input"
                  value={formData.game_date}
                  onChange={(e) => setFormData({ ...formData, game_date: e.target.value })}
                />
              </div>
              <div>
                <label className="label">Court Level</label>
                <select
                  className="input"
                  value={formData.court_level}
                  onChange={(e) => setFormData({ ...formData, court_level: e.target.value })}
                >
                  {COURT_LEVELS.map((l) => (
                    <option key={l} value={l}>{l.replace("_", " ")}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label">Team 1 Jersey (description)</label>
                <input
                  className="input"
                  placeholder="e.g. white shirt"
                  value={formData.home_team1_jersey}
                  onChange={(e) => setFormData({ ...formData, home_team1_jersey: e.target.value })}
                />
              </div>
              <div>
                <label className="label">Team 2 Jersey (description)</label>
                <input
                  className="input"
                  placeholder="e.g. dark blue shirt"
                  value={formData.away_team2_jersey}
                  onChange={(e) => setFormData({ ...formData, away_team2_jersey: e.target.value })}
                />
              </div>
              <div className="flex items-center gap-2 sm:col-span-2">
                <input
                  type="checkbox"
                  id="halfcourt"
                  checked={formData.is_half_court}
                  onChange={(e) => setFormData({ ...formData, is_half_court: e.target.checked })}
                />
                <label htmlFor="halfcourt" className="text-sm font-medium text-gray-700">
                  Half-court game
                </label>
              </div>
              {formError && (
                <p className="sm:col-span-2 rounded-lg bg-red-50 px-4 py-2 text-sm text-red-600 ring-1 ring-red-200">
                  {formError}
                </p>
              )}
              <div className="flex gap-3 sm:col-span-2">
                <button type="submit" className="btn-primary" disabled={creating}>
                  {creating ? "Creating…" : "Create"}
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => { setShowForm(false); setFormError(null); }}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {loading ? (
          <div className="text-center py-20 text-gray-400">Loading…</div>
        ) : games.length === 0 ? (
          <div className="text-center py-20 text-gray-400">No games yet. Create one above!</div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {games.map((g) => (
              <Link
                key={g.id}
                href={`/games/${g.id}`}
                className="card hover:shadow-md transition-shadow block"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <span className="inline-block rounded-full bg-primary-50 px-2.5 py-0.5 text-xs font-semibold text-primary-700">
                      {g.court_level.replace("_", " ")}
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
