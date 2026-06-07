"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { listMatchups } from "@/lib/api";
import { Swords, Loader2, ChevronRight, Plus } from "lucide-react";

interface Matchup {
  id: string; name: string; status: string; scheduled_at?: string;
  game_date?: string; created_at: string;
}

export default function MatchupsPage() {
  const router = useRouter();
  const [matchups, setMatchups] = useState<Matchup[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listMatchups()
      .then(setMatchups)
      .catch(() => router.replace("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  return (
    <AppShell title="Matchup Workspace" subtitle="Connected workflow — scouting, simulation, plays, and live tracking in one place">
      <div className="max-w-3xl mx-auto space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Swords size={20} className="text-primary-600" />
            <h2 className="text-lg font-bold text-slate-800">All Matchups</h2>
          </div>
          <Link href="/game-day" className="btn-primary btn-sm">
            <Plus size={14} /> New Matchup
          </Link>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={24} className="animate-spin text-slate-400" />
          </div>
        ) : matchups.length === 0 ? (
          <div className="card text-center py-12">
            <Swords size={32} className="text-slate-200 mx-auto mb-3" />
            <p className="text-slate-400 text-sm">No matchups yet. Create one in Game Day.</p>
          </div>
        ) : (
          <div className="card p-0 divide-y divide-slate-50">
            {matchups.map(m => (
              <Link key={m.id} href={`/matchups/${m.id}`}
                className="flex items-center gap-4 px-5 py-4 hover:bg-slate-50 transition-colors group">
                <div className="h-10 w-10 rounded-xl bg-indigo-50 flex items-center justify-center flex-shrink-0">
                  <Swords size={18} className="text-indigo-500" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-800 group-hover:text-primary-700 truncate">{m.name}</p>
                  <p className="text-xs text-slate-400">
                    {m.scheduled_at ? new Date(m.scheduled_at).toLocaleDateString() : m.game_date ?? "No date"} · {m.status}
                  </p>
                </div>
                <ChevronRight size={16} className="text-slate-300 group-hover:text-slate-500" />
              </Link>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
