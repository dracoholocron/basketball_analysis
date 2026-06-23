"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import {
  listPlayers, createPlayer, updatePlayer, deletePlayer, uploadPlayerPhoto, listTeams,
  listTeamDivisions, listPlayerDivisions, assignPlayerToDivision,
  unassignPlayerFromDivision, type Division,
} from "@/lib/api";
import {
  UserCircle2, PlusCircle, Loader2, Pencil, Trash2, X, Check,
  ChevronLeft, Layers, ImagePlus,
} from "lucide-react";
import { clsx } from "clsx";

interface Team { id: string; name: string; }
interface Player {
  id: string;
  name: string;
  jersey_number?: string;
  position?: string;
  team_id?: string;
  height_cm?: number;
  weight_kg?: number;
  photo_url?: string | null;
}

const POSITIONS = ["PG", "SG", "SF", "PF", "C"];

export default function AdminPlayersPage() {
  return (
    <Suspense>
      <AdminPlayersContent />
    </Suspense>
  );
}

function AdminPlayersContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filterTeam = searchParams.get("team_id") ?? "";

  const [players, setPlayers] = useState<Player[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [divPlayer, setDivPlayer] = useState<Player | null>(null);

  const emptyForm = { name: "", jersey_number: "", position: "", team_id: filterTeam, height_cm: "", weight_kg: "" };
  const [form, setForm] = useState<Record<string, string>>(emptyForm);
  const [saving, setSaving] = useState(false);

  const fetchPlayers = async () => {
    try {
      const [pl, tm] = await Promise.all([
        listPlayers(filterTeam || undefined),
        listTeams().then(d => d.items ?? d),
      ]);
      setPlayers(Array.isArray(pl) ? pl : pl.items ?? []);
      setTeams(tm);
    } catch {
      router.replace("/login");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchPlayers(); }, [filterTeam]);

  const teamName = (id?: string) => teams.find(t => t.id === id)?.name ?? "—";

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        name: form.name,
        jersey_number: form.jersey_number || null,
        position: form.position || null,
        team_id: form.team_id || null,
        height_cm: form.height_cm ? Number(form.height_cm) : null,
        weight_kg: form.weight_kg ? Number(form.weight_kg) : null,
      };
      if (editingId) {
        const updated = await updatePlayer(editingId, payload);
        setPlayers(prev => prev.map(p => p.id === editingId ? updated : p));
      } else {
        const created = await createPlayer(payload);
        setPlayers(prev => [created, ...prev]);
      }
      setShowForm(false);
      setEditingId(null);
      setForm(emptyForm);
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  }

  function startEdit(player: Player) {
    setEditingId(player.id);
    setForm({
      name: player.name,
      jersey_number: player.jersey_number ?? "",
      position: player.position ?? "",
      team_id: player.team_id ?? "",
      height_cm: player.height_cm?.toString() ?? "",
      weight_kg: player.weight_kg?.toString() ?? "",
    });
    setShowForm(true);
  }

  async function handlePhotoUpload(id: string, file: File) {
    try {
      const updated = await uploadPlayerPhoto(id, file);
      setPlayers(prev => prev.map(p => p.id === id ? { ...p, ...updated } : p));
    } catch {
      /* ignore — backend validates content type */
    }
  }

  async function handleDelete(id: string) {
    setDeleting(id);
    try {
      await deletePlayer(id);
      setPlayers(prev => prev.filter(p => p.id !== id));
    } catch {
      /* ignore */
    } finally {
      setDeleting(null);
    }
  }

  return (
    <AppShell title="Jugadores" subtitle="Gestión del roster por equipo">
      <div className="max-w-5xl mx-auto space-y-5">
        {/* Back + actions */}
        <div className="flex items-center justify-between">
          <Link href="/admin" className="flex items-center gap-1 text-sm text-slate-400 hover:text-white">
            <ChevronLeft size={16} /> Admin
          </Link>
          <button
            onClick={() => { setShowForm(v => !v); setEditingId(null); setForm(emptyForm); }}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium"
          >
            <PlusCircle size={16} /> Nuevo jugador
          </button>
        </div>

        {/* Team filter */}
        {teams.length > 0 && (
          <div className="flex gap-2 flex-wrap">
            <Link
              href="/admin/players"
              className={clsx("px-3 py-1 text-sm rounded-full border transition-colors",
                !filterTeam ? "bg-blue-600 border-blue-500 text-white" : "border-slate-600 text-slate-400 hover:text-white")}
            >
              Todos
            </Link>
            {teams.map(t => (
              <Link key={t.id} href={`/admin/players?team_id=${t.id}`}
                className={clsx("px-3 py-1 text-sm rounded-full border transition-colors",
                  filterTeam === t.id ? "bg-blue-600 border-blue-500 text-white" : "border-slate-600 text-slate-400 hover:text-white")}
              >
                {t.name}
              </Link>
            ))}
          </div>
        )}

        {/* Form */}
        {showForm && (
          <form onSubmit={handleSave} className="bg-slate-800 rounded-xl p-5 space-y-4 border border-slate-700">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-white">{editingId ? "Editar jugador" : "Nuevo jugador"}</h3>
              <button type="button" onClick={() => { setShowForm(false); setEditingId(null); }}>
                <X size={18} className="text-slate-400 hover:text-white" />
              </button>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {[
                { key: "name", placeholder: "Nombre *", required: true },
                { key: "jersey_number", placeholder: "#Dorsal" },
                { key: "height_cm", placeholder: "Altura (cm)", type: "number" },
                { key: "weight_kg", placeholder: "Peso (kg)", type: "number" },
              ].map(({ key, placeholder, required, type }) => (
                <input
                  key={key}
                  placeholder={placeholder}
                  required={required}
                  type={type ?? "text"}
                  value={form[key]}
                  onChange={e => setForm(p => ({ ...p, [key]: e.target.value }))}
                  className="bg-slate-700 text-white text-sm rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-blue-500"
                />
              ))}
              <select
                value={form.position}
                onChange={e => setForm(p => ({ ...p, position: e.target.value }))}
                className="bg-slate-700 text-white text-sm rounded-lg px-3 py-2"
              >
                <option value="">Posición…</option>
                {POSITIONS.map(pos => <option key={pos} value={pos}>{pos}</option>)}
              </select>
              <select
                value={form.team_id}
                onChange={e => setForm(p => ({ ...p, team_id: e.target.value }))}
                className="bg-slate-700 text-white text-sm rounded-lg px-3 py-2"
              >
                <option value="">Sin equipo</option>
                {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => { setShowForm(false); setEditingId(null); }}
                className="px-4 py-2 text-sm text-slate-400 hover:text-white">
                Cancelar
              </button>
              <button type="submit" disabled={saving}
                className="flex items-center gap-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium disabled:opacity-50">
                {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                {editingId ? "Guardar" : "Crear"}
              </button>
            </div>
          </form>
        )}

        {/* Players list */}
        {loading ? (
          <div className="flex justify-center py-16"><Loader2 className="animate-spin text-blue-500" size={28} /></div>
        ) : players.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-slate-500 gap-3">
            <UserCircle2 size={48} className="opacity-30" />
            <p className="text-sm">Sin jugadores registrados.</p>
          </div>
        ) : (
          <div className="bg-slate-800 rounded-xl overflow-hidden">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-left text-xs text-slate-400">
                  {["#", "Nombre", "Posición", "Equipo", "Altura", "Peso", ""].map(h => (
                    <th key={h} className="px-4 py-3 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {players.map(p => (
                  <tr key={p.id} className="hover:bg-slate-700/50 transition-colors">
                    <td className="px-4 py-3 font-mono font-bold text-slate-300">{p.jersey_number ?? "—"}</td>
                    <td className="px-4 py-3 font-medium">
                      <div className="flex items-center gap-2">
                        <label className="cursor-pointer inline-flex items-center justify-center h-8 w-8 rounded-lg bg-slate-700 hover:bg-slate-600 overflow-hidden shrink-0" title="Subir/cambiar foto">
                          {p.photo_url ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={p.photo_url} alt={p.name} className="h-8 w-8 object-cover" />
                          ) : (
                            <ImagePlus size={13} className="text-slate-400" />
                          )}
                          <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                            onChange={(e) => { const f = e.target.files?.[0]; if (f) handlePhotoUpload(p.id, f); }} />
                        </label>
                        <Link href={`/players/${p.id}`} className="text-blue-400 hover:underline">{p.name}</Link>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-300">{p.position ?? "—"}</td>
                    <td className="px-4 py-3 text-slate-300">{teamName(p.team_id)}</td>
                    <td className="px-4 py-3 text-slate-400">{p.height_cm ? `${p.height_cm} cm` : "—"}</td>
                    <td className="px-4 py-3 text-slate-400">{p.weight_kg ? `${p.weight_kg} kg` : "—"}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 justify-end">
                        <button onClick={() => setDivPlayer(p)} disabled={!p.team_id}
                          title={p.team_id ? "Divisiones" : "Asigna un equipo primero"}
                          className="text-slate-400 hover:text-purple-400 transition-colors disabled:opacity-30">
                          <Layers size={15} />
                        </button>
                        <button onClick={() => startEdit(p)} className="text-slate-400 hover:text-white transition-colors">
                          <Pencil size={15} />
                        </button>
                        <button
                          onClick={() => handleDelete(p.id)}
                          disabled={deleting === p.id}
                          className="text-slate-500 hover:text-red-400 transition-colors disabled:opacity-50"
                        >
                          {deleting === p.id ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {divPlayer && (
        <DivisionAssignModal player={divPlayer} onClose={() => setDivPlayer(null)} />
      )}
    </AppShell>
  );
}

function DivisionAssignModal({ player, onClose }: { player: Player; onClose: () => void }) {
  const [teamDivs, setTeamDivs] = useState<Division[]>([]);
  const [assigned, setAssigned] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!player.team_id) { setLoading(false); return; }
    Promise.all([
      listTeamDivisions(player.team_id),
      listPlayerDivisions(player.id),
    ]).then(([td, pd]) => {
      setTeamDivs(td);
      setAssigned(new Set(pd.map((d) => d.id)));
    }).catch(() => null).finally(() => setLoading(false));
  }, [player]);

  async function toggle(divId: string) {
    setBusy(divId);
    try {
      if (assigned.has(divId)) {
        await unassignPlayerFromDivision(divId, player.id);
        setAssigned((s) => { const n = new Set(s); n.delete(divId); return n; });
      } else {
        await assignPlayerToDivision(divId, player.id);
        setAssigned((s) => new Set(s).add(divId));
      }
    } catch { /* ignore */ } finally { setBusy(null); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="bg-slate-800 rounded-xl border border-slate-700 w-full max-w-md p-5 space-y-4"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-white flex items-center gap-2">
            <Layers size={18} className="text-purple-400" /> Divisiones de {player.name}
          </h3>
          <button onClick={onClose}><X size={18} className="text-slate-400 hover:text-white" /></button>
        </div>

        {loading ? (
          <div className="flex justify-center py-8"><Loader2 className="animate-spin text-blue-500" size={24} /></div>
        ) : teamDivs.length === 0 ? (
          <p className="text-sm text-slate-400 py-4 text-center">
            El equipo de este jugador no tiene divisiones. Créalas en <strong>Equipos</strong>.
          </p>
        ) : (
          <ul className="space-y-2">
            {teamDivs.map((d) => (
              <li key={d.id}>
                <label className="flex items-center gap-3 px-3 py-2 rounded-lg bg-slate-700/50 hover:bg-slate-700 cursor-pointer">
                  <input type="checkbox" checked={assigned.has(d.id)} disabled={busy === d.id}
                    onChange={() => toggle(d.id)} className="accent-purple-500 w-4 h-4" />
                  <span className="text-sm text-white">{d.name}</span>
                  {d.category && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300">
                      {d.category.replace("_", " ")}
                    </span>
                  )}
                  {busy === d.id && <Loader2 size={14} className="animate-spin text-slate-400 ml-auto" />}
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
