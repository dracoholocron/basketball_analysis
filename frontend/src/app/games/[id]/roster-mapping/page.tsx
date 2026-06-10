"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import {
  getPlayerMapping, putPlayerMapping,
  type PlayerMapping, type MappingIdentity, type RosterPlayer, type PlayerMapItem,
} from "@/lib/api";
import { ArrowLeft, Check, Loader2, Save, UserCheck, Users } from "lucide-react";
import { clsx } from "clsx";

// Per-row local choice: either an existing player id, or "new" to create from dorsal.
type Choice = { mode: "none" | "existing" | "new"; player_id?: string; name?: string };

export default function RosterMappingPage() {
  const { id: gameId } = useParams<{ id: string }>();
  const [data, setData] = useState<PlayerMapping | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [choices, setChoices] = useState<Record<number, Choice>>({});
  const [onlyDorsal, setOnlyDorsal] = useState(true);

  const load = async () => {
    try {
      const d = await getPlayerMapping(gameId);
      setData(d);
      const init: Record<number, Choice> = {};
      for (const it of d.identities) {
        init[it.track_id] = it.player_id
          ? { mode: "existing", player_id: it.player_id }
          : { mode: "none" };
      }
      setChoices(init);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "No se pudo cargar el mapeo");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (gameId) load(); }, [gameId]);

  const rosterFor = (teamId?: number | null): RosterPlayer[] =>
    teamId === 1 ? (data?.home_roster ?? []) : teamId === 2 ? (data?.away_roster ?? []) : [];

  const teamName = (teamId?: number | null): string =>
    teamId === 1 ? (data?.home_team?.name ?? "Local")
      : teamId === 2 ? (data?.away_team?.name ?? "Visitante") : "?";

  const setChoice = (trackId: number, c: Choice) =>
    setChoices((prev) => ({ ...prev, [trackId]: c }));

  const handleSave = async () => {
    if (!data) return;
    setSaving(true); setError(null);
    try {
      const mappings: PlayerMapItem[] = [];
      for (const it of data.identities) {
        const c = choices[it.track_id];
        if (!c || c.mode === "none") continue;
        if (c.mode === "existing" && c.player_id) {
          mappings.push({ track_id: it.track_id, player_id: c.player_id });
        } else if (c.mode === "new" && c.name?.trim()) {
          mappings.push({
            track_id: it.track_id, new_player_name: c.name.trim(),
            team_id: it.team_id, jersey_number: it.jersey_number,
          });
        }
      }
      await putPlayerMapping(gameId, mappings);
      setSaved(true);
      await load();
      setTimeout(() => setSaved(false), 2000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "No se pudo guardar");
    } finally {
      setSaving(false);
    }
  };

  const identities = (data?.identities ?? []).filter((i) => !onlyDorsal || i.jersey_number);

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto px-4 py-8 space-y-5">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <Link href={`/games/${gameId}`} className="p-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300">
              <ArrowLeft size={16} />
            </Link>
            <div>
              <h1 className="text-xl font-bold text-white flex items-center gap-2">
                <UserCheck size={20} className="text-emerald-400" /> Asignar jugadores
              </h1>
              <p className="text-sm text-slate-400">
                Vincula cada dorsal detectado con un jugador del roster (o créalo). No re-analiza el video.
              </p>
            </div>
          </div>
          <button
            onClick={handleSave}
            disabled={saving || !data}
            className={clsx("flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium",
              saved ? "bg-green-600 text-white" : "bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50")}
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <Check size={14} /> : <Save size={14} />}
            {saved ? "Guardado" : "Guardar mapeo"}
          </button>
        </div>

        {error && (
          <div className="px-4 py-3 rounded-lg bg-red-900/30 border border-red-700/50 text-sm text-red-300">{error}</div>
        )}

        <div className="flex items-center gap-3">
          <button onClick={() => setOnlyDorsal(v => !v)}
            className={clsx("px-3 py-1.5 rounded-lg text-xs font-medium border",
              onlyDorsal ? "bg-emerald-600 border-emerald-500 text-white" : "border-slate-600 text-slate-300")}>
            {onlyDorsal ? "Solo con dorsal" : "Mostrando todas las identidades"}
          </button>
          <span className="text-xs text-slate-500">
            {data ? `${data.identities.filter(i => i.jersey_number).length} con dorsal · ${data.identities.length} totales` : ""}
          </span>
        </div>

        {loading ? (
          <div className="flex justify-center py-16"><Loader2 className="animate-spin text-blue-500" size={28} /></div>
        ) : (
          <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-left text-xs text-slate-400">
                  {["Detectado", "Equipo", "Min.", "Asignar a jugador"].map(h => (
                    <th key={h} className="px-4 py-3 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {identities.map((it: MappingIdentity) => {
                  const c = choices[it.track_id] ?? { mode: "none" };
                  const roster = rosterFor(it.team_id);
                  return (
                    <tr key={it.track_id} className="hover:bg-slate-700/40">
                      <td className="px-4 py-3 font-mono font-semibold text-white">
                        {it.jersey_number ? `#${it.jersey_number}` : (it.display_label ?? `#${it.track_id}`)}
                      </td>
                      <td className="px-4 py-3 text-slate-300">{teamName(it.team_id)}</td>
                      <td className="px-4 py-3 text-slate-400">{it.minutes_played.toFixed(1)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2 flex-wrap">
                          <select
                            value={c.mode === "existing" ? (c.player_id ?? "") : c.mode === "new" ? "__new__" : ""}
                            onChange={(e) => {
                              const v = e.target.value;
                              if (v === "") setChoice(it.track_id, { mode: "none" });
                              else if (v === "__new__") setChoice(it.track_id, { mode: "new", name: it.jersey_number ? `Jugador #${it.jersey_number}` : "" });
                              else setChoice(it.track_id, { mode: "existing", player_id: v });
                            }}
                            className="bg-slate-900 border border-slate-600 rounded-lg px-2 py-1.5 text-sm text-white"
                          >
                            <option value="">— sin asignar —</option>
                            {roster.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.name}{p.jersey_number ? ` (#${p.jersey_number})` : ""}
                              </option>
                            ))}
                            <option value="__new__">+ Crear jugador nuevo…</option>
                          </select>
                          {c.mode === "new" && (
                            <input
                              value={c.name ?? ""}
                              onChange={(e) => setChoice(it.track_id, { mode: "new", name: e.target.value })}
                              placeholder="Nombre del jugador"
                              className="bg-slate-900 border border-slate-600 rounded-lg px-2 py-1.5 text-sm text-white"
                            />
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {identities.length === 0 && (
                  <tr><td colSpan={4} className="px-4 py-10 text-center text-slate-500">
                    <Users className="mx-auto mb-2 opacity-40" size={28} />
                    No hay identidades para mostrar.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
  );
}
