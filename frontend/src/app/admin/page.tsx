"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Navbar from "@/components/Navbar";
import {
  listOrganizations,
  createOrganization,
  listSeasons,
  createSeason,
  listTeams,
  createTeam,
} from "@/lib/api";

interface Org { id: string; name: string; slug: string; }
interface Season { id: string; name: string; year: number; organization_id?: string; }
interface Team { id: string; name: string; slug: string; season_id?: string; jersey_description?: string; }

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card space-y-4">
      <h2 className="text-lg font-semibold border-b border-gray-100 pb-2">{title}</h2>
      {children}
    </section>
  );
}

export default function AdminPage() {
  const router = useRouter();
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [seasons, setSeasons] = useState<Season[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [orgForm, setOrgForm] = useState({ name: "", slug: "" });
  const [seasonForm, setSeasonForm] = useState({ name: "", year: new Date().getFullYear(), organization_id: "" });
  const [teamForm, setTeamForm] = useState({ name: "", slug: "", season_id: "", jersey_description: "" });

  const [saving, setSaving] = useState<string | null>(null);

  const reload = () => {
    listOrganizations()
      .then((d) => { const items = d.items ?? d; setOrgs(items); if (items.length && !seasonForm.organization_id) setSeasonForm(f => ({ ...f, organization_id: items[0].id })); })
      .catch(() => null);
    listSeasons()
      .then((d) => { const items = d.items ?? d; setSeasons(items); if (items.length && !teamForm.season_id) setTeamForm(f => ({ ...f, season_id: items[0].id })); })
      .catch(() => null);
    listTeams()
      .then((d) => setTeams(d.items ?? d))
      .catch(() => null);
  };

  useEffect(() => {
    reload();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleOrg(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving("org");
    try {
      await createOrganization({ name: orgForm.name, slug: orgForm.slug });
      setOrgForm({ name: "", slug: "" });
      reload();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create organization");
    } finally { setSaving(null); }
  }

  async function handleSeason(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving("season");
    try {
      await createSeason({ name: seasonForm.name, year: Number(seasonForm.year), organization_id: seasonForm.organization_id || undefined });
      setSeasonForm(f => ({ ...f, name: "" }));
      reload();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create season");
    } finally { setSaving(null); }
  }

  async function handleTeam(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving("team");
    try {
      await createTeam({
        name: teamForm.name,
        slug: teamForm.slug,
        season_id: teamForm.season_id || undefined,
        jersey_description: teamForm.jersey_description || undefined,
      });
      setTeamForm(f => ({ ...f, name: "", slug: "", jersey_description: "" }));
      reload();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to create team");
    } finally { setSaving(null); }
  }

  return (
    <>
      <Navbar />
      <main className="mx-auto max-w-5xl px-4 py-8 space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Admin</h1>
          <button className="btn-secondary text-sm" onClick={() => router.push("/games")}>
            ← Back to Games
          </button>
        </div>

        {error && (
          <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600 ring-1 ring-red-200">{error}</p>
        )}

        {/* Organizations */}
        <Section title="Organizations">
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                  <th className="pb-2 pr-4">Name</th>
                  <th className="pb-2 pr-4">Slug</th>
                  <th className="pb-2 font-mono">ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {orgs.length === 0 && (
                  <tr><td colSpan={3} className="py-3 text-gray-400 text-center">No organizations yet</td></tr>
                )}
                {orgs.map((o) => (
                  <tr key={o.id}>
                    <td className="py-2 pr-4 font-medium">{o.name}</td>
                    <td className="py-2 pr-4 text-gray-500">{o.slug}</td>
                    <td className="py-2 font-mono text-xs text-gray-400">{o.id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <form onSubmit={handleOrg} className="grid grid-cols-1 gap-3 sm:grid-cols-3 mt-2">
            <div>
              <label className="label">Name</label>
              <input className="input" required placeholder="My School" value={orgForm.name}
                onChange={(e) => setOrgForm({ ...orgForm, name: e.target.value })} />
            </div>
            <div>
              <label className="label">Slug</label>
              <input className="input" required placeholder="my-school" pattern="^[a-z0-9-]+" value={orgForm.slug}
                onChange={(e) => setOrgForm({ ...orgForm, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") })} />
            </div>
            <div className="flex items-end">
              <button type="submit" className="btn-primary w-full justify-center" disabled={saving === "org"}>
                {saving === "org" ? "Saving…" : "Add Organization"}
              </button>
            </div>
          </form>
        </Section>

        {/* Seasons */}
        <Section title="Seasons">
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                  <th className="pb-2 pr-4">Name</th>
                  <th className="pb-2 pr-4">Year</th>
                  <th className="pb-2 font-mono">ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {seasons.length === 0 && (
                  <tr><td colSpan={3} className="py-3 text-gray-400 text-center">No seasons yet</td></tr>
                )}
                {seasons.map((s) => (
                  <tr key={s.id}>
                    <td className="py-2 pr-4 font-medium">{s.name}</td>
                    <td className="py-2 pr-4 text-gray-500">{s.year}</td>
                    <td className="py-2 font-mono text-xs text-gray-400">{s.id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <form onSubmit={handleSeason} className="grid grid-cols-1 gap-3 sm:grid-cols-4 mt-2">
            <div>
              <label className="label">Name</label>
              <input className="input" required placeholder="Season 2026" value={seasonForm.name}
                onChange={(e) => setSeasonForm({ ...seasonForm, name: e.target.value })} />
            </div>
            <div>
              <label className="label">Year</label>
              <input type="number" className="input" required min={2000} max={2100} value={seasonForm.year}
                onChange={(e) => setSeasonForm({ ...seasonForm, year: Number(e.target.value) })} />
            </div>
            <div>
              <label className="label">Organization</label>
              <select className="input" value={seasonForm.organization_id}
                onChange={(e) => setSeasonForm({ ...seasonForm, organization_id: e.target.value })}>
                <option value="">— none —</option>
                {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </select>
            </div>
            <div className="flex items-end">
              <button type="submit" className="btn-primary w-full justify-center" disabled={saving === "season"}>
                {saving === "season" ? "Saving…" : "Add Season"}
              </button>
            </div>
          </form>
        </Section>

        {/* Teams */}
        <Section title="Teams">
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 text-left text-xs text-gray-500">
                  <th className="pb-2 pr-4">Name</th>
                  <th className="pb-2 pr-4">Slug</th>
                  <th className="pb-2 pr-4">Jersey</th>
                  <th className="pb-2 font-mono">ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {teams.length === 0 && (
                  <tr><td colSpan={4} className="py-3 text-gray-400 text-center">No teams yet</td></tr>
                )}
                {teams.map((t) => (
                  <tr key={t.id}>
                    <td className="py-2 pr-4 font-medium">{t.name}</td>
                    <td className="py-2 pr-4 text-gray-500">{t.slug}</td>
                    <td className="py-2 pr-4 text-gray-500 text-xs">{t.jersey_description ?? "—"}</td>
                    <td className="py-2 font-mono text-xs text-gray-400">{t.id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <form onSubmit={handleTeam} className="grid grid-cols-1 gap-3 sm:grid-cols-4 mt-2">
            <div>
              <label className="label">Name</label>
              <input className="input" required placeholder="Home Team" value={teamForm.name}
                onChange={(e) => setTeamForm({ ...teamForm, name: e.target.value })} />
            </div>
            <div>
              <label className="label">Slug</label>
              <input className="input" required placeholder="home-team" value={teamForm.slug}
                onChange={(e) => setTeamForm({ ...teamForm, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") })} />
            </div>
            <div>
              <label className="label">Season</label>
              <select className="input" value={teamForm.season_id}
                onChange={(e) => setTeamForm({ ...teamForm, season_id: e.target.value })}>
                <option value="">— none —</option>
                {seasons.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Jersey Description</label>
              <input className="input" placeholder="white jersey" value={teamForm.jersey_description}
                onChange={(e) => setTeamForm({ ...teamForm, jersey_description: e.target.value })} />
            </div>
            <div className="sm:col-span-4 flex justify-end">
              <button type="submit" className="btn-primary" disabled={saving === "team"}>
                {saving === "team" ? "Saving…" : "Add Team"}
              </button>
            </div>
          </form>
        </Section>
      </main>
    </>
  );
}
