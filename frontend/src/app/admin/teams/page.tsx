"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { listTeams, createTeam, listOrganizations, getMe } from "@/lib/api";
import { PlusCircle, Users, ChevronLeft, AlertCircle, Building2 } from "lucide-react";

interface Team { id: string; name: string; level?: string; jersey_description?: string; organization_id: string; }
interface Org { id: string; name: string; }

const LEVELS = ["mini_basket", "primaria", "secundaria", "juvenil", "nba"];

export default function TeamsPage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [currentOrg, setCurrentOrg] = useState<Org | null>(null);
  const [form, setForm] = useState({ name: "", jersey_description: "", level: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
                  <th className="pb-2 pr-4 text-left text-xs font-semibold text-slate-400 uppercase">Name</th>
                  <th className="pb-2 pr-4 text-left text-xs font-semibold text-slate-400 uppercase">Level</th>
                  <th className="pb-2 pr-4 text-left text-xs font-semibold text-slate-400 uppercase">Jersey</th>
                  <th className="pb-2 text-left text-xs font-semibold text-slate-400 uppercase font-mono">ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {teams.map((t) => (
                  <tr key={t.id} className="table-row">
                    <td className="table-cell font-medium">{t.name}</td>
                    <td className="table-cell text-slate-500 text-xs uppercase">{t.level ?? "—"}</td>
                    <td className="table-cell text-xs text-slate-500">{t.jersey_description ?? "—"}</td>
                    <td className="table-cell font-mono text-xs text-slate-400">{t.id.slice(0, 12)}…</td>
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
      </div>
    </AppShell>
  );
}
