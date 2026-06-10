"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { getTeamStats } from "@/lib/api";
import { ArrowLeft, Loader2, Shield } from "lucide-react";

interface TeamPlayerRow {
  player_id: string; name: string; jersey_number?: string | null;
  games: number; ppg?: number | null; minutes_played: number; distance_m: number;
  fg_pct?: number | null; shots_made_cv: number; shots_attempted_cv: number;
  rebounds_cv: number; steals_cv: number;
}
interface TeamStats {
  team_id: string; name: string; seasons: string[]; games: number;
  totals: { pts: number; fgm: number; fga: number; distance_m: number;
    shots_made_cv: number; shots_attempted_cv: number; rebounds_cv: number; steals_cv: number; };
  players: TeamPlayerRow[];
}

export default function TeamProfilePage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<TeamStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [season, setSeason] = useState<string>("");

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getTeamStats(id, season || undefined)
      .then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [id, season]);

  const pct = (v?: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
        <Link href="/admin/teams" className="text-sm text-slate-400 hover:text-white flex items-center gap-1">
          <ArrowLeft size={14} /> Equipos
        </Link>

        {loading ? (
          <div className="flex justify-center py-16"><Loader2 className="animate-spin text-blue-500" size={28} /></div>
        ) : !data ? (
          <p className="text-slate-400">No se encontraron estadísticas para este equipo.</p>
        ) : (
          <>
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div className="flex items-center gap-3">
                <Shield size={36} className="text-blue-400" />
                <div>
                  <h1 className="text-2xl font-bold text-white">{data.name}</h1>
                  <p className="text-sm text-slate-400">{data.games} juegos · {data.players.length} jugadores</p>
                </div>
              </div>
              {data.seasons.length > 0 && (
                <select value={season} onChange={(e) => setSeason(e.target.value)}
                  className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-white">
                  <option value="">Todas las temporadas</option>
                  {data.seasons.map((s) => <option key={s} value={s}>{s.slice(0, 8)}</option>)}
                </select>
              )}
            </div>

            <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-x-auto">
              <div className="px-4 py-3 text-sm font-semibold text-white border-b border-slate-700">Roster — agregados</div>
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-400 border-b border-slate-700">
                    {["Jugador", "J", "PPG", "FG%", "Min", "Dist (km)", "Tiros CV", "Reb CV", "Robos CV"].map(h => (
                      <th key={h} className="px-4 py-2 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/60">
                  {data.players.map((p) => (
                    <tr key={p.player_id} className="hover:bg-slate-700/40">
                      <td className="px-4 py-2">
                        <Link href={`/players/${p.player_id}`} className="text-blue-400 hover:underline font-medium">
                          {p.name}{p.jersey_number ? ` #${p.jersey_number}` : ""}
                        </Link>
                      </td>
                      <td className="px-4 py-2 text-slate-300">{p.games}</td>
                      <td className="px-4 py-2 text-slate-200">{p.ppg != null ? p.ppg.toFixed(1) : "—"}</td>
                      <td className="px-4 py-2 text-slate-200">{pct(p.fg_pct)}</td>
                      <td className="px-4 py-2 text-slate-200">{p.minutes_played.toFixed(0)}</td>
                      <td className="px-4 py-2 text-slate-200">{(p.distance_m / 1000).toFixed(2)}</td>
                      <td className="px-4 py-2 text-slate-200">{p.shots_made_cv}/{p.shots_attempted_cv}</td>
                      <td className="px-4 py-2 text-slate-200">{p.rebounds_cv}</td>
                      <td className="px-4 py-2 text-slate-200">{p.steals_cv}</td>
                    </tr>
                  ))}
                  {data.players.length === 0 && (
                    <tr><td colSpan={9} className="px-4 py-10 text-center text-slate-500">
                      Sin estadísticas. Analiza juegos y asigna jugadores a sus dorsales.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
