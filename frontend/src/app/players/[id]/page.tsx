"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { getPlayerStats } from "@/lib/api";
import { ArrowLeft, Loader2, UserCircle2, Activity, Target, Gauge, Route } from "lucide-react";

interface Agg {
  games: number; pts: number; ppg?: number | null;
  fg_pct?: number | null; fg_pct_cv?: number | null; fg3_pct?: number | null;
  minutes_played: number; distance_m: number; avg_speed_kmh: number; max_speed_kmh: number;
  shots_made_cv: number; shots_attempted_cv: number; shots_missed_cv: number;
  rebounds_cv: number; steals_cv: number; passes_cv: number;
}
interface GameRow {
  game_id: string; season_id?: string | null; source: string; minutes_played: number;
  pts?: number | null; fgm?: number | null; fga?: number | null; reb?: number | null;
  ast?: number | null; stl?: number | null; distance_m: number; max_speed_kmh: number;
  shots_attempted_cv: number; shots_made_cv: number; rebounds_cv: number; steals_cv: number;
}
interface PlayerStats {
  player_id: string; name: string; jersey_number?: string | null;
  seasons: string[]; aggregate: Agg; games: GameRow[];
}

function Stat({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <div className="flex items-center gap-2 text-slate-400 text-xs mb-1">{icon}{label}</div>
      <div className="text-2xl font-bold text-white">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
}

export default function PlayerProfilePage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<PlayerStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [season, setSeason] = useState<string>("");

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getPlayerStats(id, season || undefined)
      .then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [id, season]);

  const a = data?.aggregate;
  const pct = (v?: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">
        <Link href="/admin/players" className="text-sm text-slate-400 hover:text-white flex items-center gap-1">
          <ArrowLeft size={14} /> Jugadores
        </Link>

        {loading ? (
          <div className="flex justify-center py-16"><Loader2 className="animate-spin text-blue-500" size={28} /></div>
        ) : !data ? (
          <p className="text-slate-400">No se encontraron estadísticas para este jugador.</p>
        ) : (
          <>
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div className="flex items-center gap-3">
                <UserCircle2 size={40} className="text-blue-400" />
                <div>
                  <h1 className="text-2xl font-bold text-white">
                    {data.name} {data.jersey_number && <span className="text-slate-400">#{data.jersey_number}</span>}
                  </h1>
                  <p className="text-sm text-slate-400">{a?.games ?? 0} juegos analizados</p>
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

            {/* Aggregate cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Stat icon={<Target size={13} />} label="PPG" value={a?.ppg != null ? a.ppg.toFixed(1) : "—"}
                sub={a?.pts ? `${a.pts} pts tot.` : "sin box score"} />
              <Stat icon={<Target size={13} />} label="FG%"
                value={pct(a?.fg_pct)}
                sub={a?.fg_pct == null && a?.fg_pct_cv != null ? `CV ${pct(a?.fg_pct_cv)}` : "box score"} />
              <Stat icon={<Activity size={13} />} label="Minutos" value={(a?.minutes_played ?? 0).toFixed(0)} />
              <Stat icon={<Route size={13} />} label="Distancia" value={`${((a?.distance_m ?? 0) / 1000).toFixed(2)} km`} />
              <Stat icon={<Gauge size={13} />} label="Vel. máx" value={`${(a?.max_speed_kmh ?? 0).toFixed(1)} km/h`} />
              <Stat icon={<Target size={13} />} label="Tiros CV (A/I)"
                value={`${a?.shots_made_cv ?? 0}/${a?.shots_attempted_cv ?? 0}`} sub={`FG% CV ${pct(a?.fg_pct_cv)}`} />
              <Stat icon={<Activity size={13} />} label="Rebotes CV" value={`${a?.rebounds_cv ?? 0}`} />
              <Stat icon={<Activity size={13} />} label="Robos CV" value={`${a?.steals_cv ?? 0}`} />
            </div>

            {/* Game log */}
            <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-x-auto">
              <div className="px-4 py-3 text-sm font-semibold text-white border-b border-slate-700">Registro por juego</div>
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-400 border-b border-slate-700">
                    {["Juego", "Fuente", "Min", "Pts", "FG", "Reb", "Dist (km)", "V.máx", "Tiros CV"].map(h => (
                      <th key={h} className="px-4 py-2 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/60">
                  {data.games.map((g) => (
                    <tr key={g.game_id} className="hover:bg-slate-700/40">
                      <td className="px-4 py-2">
                        <Link href={`/games/${g.game_id}`} className="text-blue-400 hover:underline font-mono">
                          {g.game_id.slice(0, 8)}
                        </Link>
                      </td>
                      <td className="px-4 py-2 text-slate-500 text-xs uppercase">{g.source}</td>
                      <td className="px-4 py-2 text-slate-200">{g.minutes_played.toFixed(0)}</td>
                      <td className="px-4 py-2 text-slate-200">{g.pts ?? "—"}</td>
                      <td className="px-4 py-2 text-slate-200">{g.fgm != null && g.fga != null ? `${g.fgm}/${g.fga}` : "—"}</td>
                      <td className="px-4 py-2 text-slate-200">{g.reb ?? "—"}</td>
                      <td className="px-4 py-2 text-slate-200">{(g.distance_m / 1000).toFixed(2)}</td>
                      <td className="px-4 py-2 text-slate-200">{g.max_speed_kmh.toFixed(1)}</td>
                      <td className="px-4 py-2 text-slate-200">{g.shots_made_cv}/{g.shots_attempted_cv}</td>
                    </tr>
                  ))}
                  {data.games.length === 0 && (
                    <tr><td colSpan={9} className="px-4 py-10 text-center text-slate-500">Sin juegos para esta temporada.</td></tr>
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
