"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { listOrganizations, createOrganization } from "@/lib/api";
import { PlusCircle, Building2, ChevronLeft, AlertCircle } from "lucide-react";

interface Org { id: string; name: string; slug: string; }

export default function OrganizationsPage() {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [form, setForm] = useState({ name: "", slug: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = () => listOrganizations()
    .then((d) => setOrgs(d.items ?? d))
    .catch(() => null);

  useEffect(() => { reload(); }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true); setError(null);
    try {
      await createOrganization({ name: form.name, slug: form.slug });
      setForm({ name: "", slug: "" });
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create organization");
    } finally {
      setSaving(false);
    }
  }

  return (
    <AppShell title="Organizations" subtitle="Manage organizations">
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
            <Building2 size={18} className="text-primary-600" />
            <h2 className="font-display font-bold text-slate-900">Organizations</h2>
          </div>
          {orgs.length === 0 ? (
            <p className="text-sm text-slate-400 py-4 text-center">No organizations yet</p>
          ) : (
            <table className="min-w-full text-sm mb-6">
              <thead>
                <tr>
                  <th className="pb-2 pr-4 text-left text-xs font-semibold text-slate-400 uppercase">Name</th>
                  <th className="pb-2 pr-4 text-left text-xs font-semibold text-slate-400 uppercase">Slug</th>
                  <th className="pb-2 text-left text-xs font-semibold text-slate-400 uppercase font-mono">ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {orgs.map((o) => (
                  <tr key={o.id} className="table-row">
                    <td className="table-cell font-medium">{o.name}</td>
                    <td className="table-cell text-slate-500">{o.slug}</td>
                    <td className="table-cell font-mono text-xs text-slate-400">{o.id.slice(0, 12)}…</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-3 sm:grid-cols-3 border-t border-slate-100 pt-5">
            <div>
              <label className="label">Name *</label>
              <input className="input" required placeholder="My School" value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <label className="label">Slug *</label>
              <input className="input" required placeholder="my-school" value={form.slug}
                onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") })} />
            </div>
            <div className="flex items-end">
              <button type="submit" className="btn-primary w-full" disabled={saving}>
                <PlusCircle size={15} />
                {saving ? "Saving…" : "Add Organization"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </AppShell>
  );
}
