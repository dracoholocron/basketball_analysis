"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { listTeams, createTeam, listOrganizations } from "@/lib/api";
import { PlusCircle, Users, ChevronLeft, AlertCircle } from "lucide-react";

interface Team { id: string; name: string; level?: string; jersey_description?: string; }
interface Org { id: string; name: string; }

const LEVELS = ["mini_basket", "primaria", "secundaria", "juvenil", "nba"];

export default function TeamsPage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [form, setForm] = useState({ name: "", organization_id: "", jersey_description: "", level: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = () => {
    listTeams().then((d) => setTeams(d.items ?? d)).catch(() => null);
    listOrganizations().then((d) => {
      const items = d.items ?? d;
      setOrgs(items);
      if (items.length && !form.organization_id) setForm(f => ({ ...f, organization_id: items[0].id }));
    }).catch(() => null);
  };

  useEffect(() => { reload(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true); setError(null);
    try {
      await createTeam({
        name: form.name,
        organization_id: form.organization_id || undefined,
        jersey_description: form.jersey_description || undefined,
        level: form.level || undefined,
      });
      setForm(f => ({ ...f, name: "", jersey_description: "", level: "" }));
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create team");
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
          <div className="flex items-center gap-2 rounded-xl bg-danger-50 px-4 py-3 text-sm text-danger-600 ring-1 ring-danger-100">
            <AlertCircle size={15} /> {error}
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
            <div>
              <label className="label">Name *</label>
              <input className="input" required placeholder="Home Team" value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <label className="label">Organization</label>
              <select className="input" value={form.organization_id}
                onChange={(e) => setForm({ ...form, organization_id: e.target.value })}>
                <option value="">— none —</option>
                {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Jersey Description</label>
              <input className="input" placeholder="white jersey" value={form.jersey_description}
                onChange={(e) => setForm({ ...form, jersey_description: e.target.value })} />
            </div>
            <div>
              <label className="label">Level</label>
              <select className="input" value={form.level}
                onChange={(e) => setForm({ ...form, level: e.target.value })}>
                <option value="">— none —</option>
                {LEVELS.map((l) => <option key={l} value={l}>{l.replace("_", " ")}</option>)}
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
