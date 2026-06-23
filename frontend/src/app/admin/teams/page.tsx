"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import {
  listTeams, createTeam, uploadTeamLogo, listOrganizations, getMe,
  listTeamDivisions, createDivision, deleteDivision, type Division,
} from "@/lib/api";
import { PlusCircle, Users, ChevronLeft, AlertCircle, Building2, Layers, Trash2, ImagePlus } from "lucide-react";

interface Team { id: string; name: string; level?: string; jersey_description?: string; organization_id: string; logo_url?: string | null; }
interface Org { id: string; name: string; }

const LEVELS = ["mini_basket", "primaria", "secundaria", "juvenil", "nba"];
const DIVISION_CATEGORIES = ["U12", "U14", "U15", "U18_mixto"];

export default function TeamsPage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [currentOrg, setCurrentOrg] = useState<Org | null>(null);
  const [form, setForm] = useState({ name: "", jersey_description: "", level: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLogoUpload(teamId: string, file: File) {
    try {
      await uploadTeamLogo(teamId, file);
      const d = await listTeams();
      setTeams(Array.isArray(d) ? d : (d.items ?? []));
    } catch {
      setError("No se pudo subir el logo (usa PNG/JPEG/WebP).");
    }
  }

  useEffect(() => {
    // Load current user's org name for display
    getMe().then((me) =>
      listOrganizations().then((orgs: Org[]) => {
        const org = (orgs as Org[]).find((o) => o.id === me.organization_id);
        setCurrentOrg(org ?? { id: me.organization_id, name: me.organization_id });
      }).catch(() => null)
    ).catch(() => null);

    listTeams().then((d: Team[] | { items: Team[] }) => {
      setTeams(Array.isArray(d) ? d : (d.items ?? []));
    }).catch(() => null);
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await createTeam({
        name: form.name,
        jersey_description: form.jersey_description || undefined,
        level: form.level || undefined,
      });
      setForm({ name: "", jersey_description: "", level: "" });
      // Refresh list
      const d = await listTeams();
      setTeams(Array.isArray(d) ? d : (d.items ?? []));
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (err instanceof Error ? err.message : "Failed to create team");
      setError(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell title="Teams" subtitle="Add and manage teams">
      <div className="max-w-3xl mx-auto space-y-5">
        <Link href="/admin" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700">
          <ChevronLeft size={15} /> Back to Admin
        </Link>

        {error && (
          <div className="flex items-center gap-2 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600 ring-1 ring-red-100">
            <AlertCircle size={15} /> {error}
          </div>
        )}

        {currentOrg && (
          <div className="flex items-center gap-2 rounded-xl bg-blue-50 px-4 py-3 text-sm text-blue-700 ring-1 ring-blue-100">
            <Building2 size={15} />
            Teams are created under your organization: <strong>{currentOrg.name}</strong>
          </div>
        )}

        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <Users size={18} className="text-green-600" />
            <h2 className="font-display font-bold text-slate-900">Teams</h2>
          </div>
          {teams.length === 0 ? (
            <p className="text-sm text-slate-400 py-4 text-center">No teams yet</p>
          ) : (
            <table className="min-w-full text-sm mb-6">
              <thead>
                <tr>
                  <th className="pb-2 pr-4 text-left text-xs font-semibold text-slate-400 uppercase">Logo</th>
                  <th className="pb-2 pr-4 text-left text-xs font-semibold text-slate-400 uppercase">Name</th>
                  <th className="pb-2 pr-4 text-left text-xs font-semibold text-slate-400 uppercase">Level</th>
                  <th className="pb-2 pr-4 text-left text-xs font-semibold text-slate-400 uppercase">Jersey</th>
                  <th className="pb-2 text-left text-xs font-semibold text-slate-400 uppercase">Stats</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {teams.map((t) => (
                  <tr key={t.id} className="table-row">
                    <td className="table-cell">
                      <label className="cursor-pointer inline-flex items-center justify-center h-9 w-9 rounded-lg bg-slate-100 hover:bg-slate-200 overflow-hidden" title="Subir/cambiar logo">
                        {t.logo_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={t.logo_url} alt={t.name} className="h-9 w-9 object-cover" />
                        ) : (
                          <ImagePlus size={15} className="text-slate-400" />
                        )}
                        <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleLogoUpload(t.id, f); }} />
                      </label>
                    </td>
                    <td className="table-cell font-medium">
                      <Link href={`/teams/${t.id}`} className="text-blue-600 hover:underline">{t.name}</Link>
                    </td>
                    <td className="table-cell text-slate-500 text-xs uppercase">{t.level ?? "—"}</td>
                    <td className="table-cell text-xs text-slate-500">{t.jersey_description ?? "—"}</td>
                    <td className="table-cell">
                      <Link href={`/teams/${t.id}`} className="text-xs text-blue-600 hover:underline">Ver stats →</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-3 sm:grid-cols-2 border-t border-slate-100 pt-5">
            <div className="sm:col-span-2">
              <label className="label">Name *</label>
              <input
                className="input"
                required
                placeholder="Home Team"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Jersey Description</label>
              <input
                className="input"
                placeholder="white jersey"
                value={form.jersey_description}
                onChange={(e) => setForm({ ...form, jersey_description: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Level</label>
              <select
                className="input"
                value={form.level}
                onChange={(e) => setForm({ ...form, level: e.target.value })}
              >
                <option value="">— none —</option>
                {LEVELS.map((l) => (
                  <option key={l} value={l}>{l.replace("_", " ")}</option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-2 flex justify-end">
              <button type="submit" className="btn-primary" disabled={saving}>
                <PlusCircle size={15} />
                {saving ? "Saving…" : "Add Team"}
              </button>
            </div>
          </form>
        </div>

        <DivisionsManager teams={teams} />
      </div>
    </AppShell>
  );
}

function DivisionsManager({ teams }: { teams: Team[] }) {
  const [teamId, setTeamId] = useState("");
  const [divs, setDivs] = useState<Division[]>([]);
  const [form, setForm] = useState({ name: "", category: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!teamId && teams.length) setTeamId(teams[0].id);
  }, [teams, teamId]);

  const refresh = (tid: string) => {
    if (!tid) return;
    listTeamDivisions(tid).then(setDivs).catch(() => setDivs([]));
  };
  useEffect(() => { refresh(teamId); }, [teamId]);

  async function addDivision(e: React.FormEvent) {
    e.preventDefault();
    if (!teamId || !form.name.trim()) return;
    setBusy(true); setError(null);
    try {
      await createDivision(teamId, { name: form.name.trim(), category: form.category || undefined });
      setForm({ name: "", category: "" });
      refresh(teamId);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof msg === "string" ? msg : "No se pudo crear la división");
    } finally {
      setBusy(false);
    }
  }

  async function removeDivision(id: string) {
    await deleteDivision(id).catch(() => null);
    refresh(teamId);
  }

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-4">
        <Layers size={18} className="text-purple-600" />
        <h2 className="font-display font-bold text-slate-900">Divisiones (grupos de edad)</h2>
      </div>
      <p className="text-xs text-slate-400 mb-3">
        Un equipo puede tener varias divisiones (U12, U14, U15, U18 mixto…). Un jugador puede estar en
        varias divisiones — se asignan desde <strong>Jugadores</strong>.
      </p>

      <div className="mb-4">
        <label className="label">Equipo</label>
        <select className="input" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
          {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-xl bg-red-50 px-4 py-2 text-sm text-red-600 ring-1 ring-red-100 mb-3">
          <AlertCircle size={15} /> {error}
        </div>
      )}

      {divs.length === 0 ? (
        <p className="text-sm text-slate-400 py-3 text-center">Sin divisiones para este equipo</p>
      ) : (
        <ul className="divide-y divide-slate-50 mb-4">
          {divs.map((d) => (
            <li key={d.id} className="flex items-center justify-between py-2">
              <div>
                <span className="font-medium text-slate-800">{d.name}</span>
                {d.category && (
                  <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-purple-50 text-purple-600">
                    {d.category.replace("_", " ")}
                  </span>
                )}
                <span className="ml-2 text-xs text-slate-400">{d.player_count} jugador(es)</span>
              </div>
              <button onClick={() => removeDivision(d.id)} className="text-slate-400 hover:text-red-500" title="Eliminar">
                <Trash2 size={15} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={addDivision} className="grid grid-cols-1 gap-3 sm:grid-cols-3 border-t border-slate-100 pt-4">
        <div className="sm:col-span-1">
          <label className="label">Nombre *</label>
          <input className="input" required placeholder="U14 A" value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div>
          <label className="label">Categoría</label>
          <select className="input" value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}>
            <option value="">— ninguna —</option>
            {DIVISION_CATEGORIES.map((c) => <option key={c} value={c}>{c.replace("_", " ")}</option>)}
          </select>
        </div>
        <div className="flex items-end justify-end">
          <button type="submit" className="btn-primary" disabled={busy || !teamId}>
            <PlusCircle size={15} /> {busy ? "…" : "Añadir división"}
          </button>
        </div>
      </form>
    </div>
  );
}
