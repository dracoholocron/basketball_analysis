"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { listModelVersions, activateModelVersion, scanModels, type ModelVersion } from "@/lib/api";
import { ChevronLeft, Loader2, RefreshCw, CheckCircle2, Circle, Boxes } from "lucide-react";
import { clsx } from "clsx";

const ROLE_LABELS: Record<string, string> = {
  player: "Detector de jugadores", ball: "Detector de balón",
  court: "Keypoints de cancha", pose: "Pose (esqueleto)",
};

export default function AdminModelsPage() {
  const [roles, setRoles] = useState<Record<string, ModelVersion[]>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  const load = async () => {
    try { setRoles((await listModelVersions()).roles ?? {}); }
    catch { setRoles({}); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const onActivate = async (v: ModelVersion) => {
    setBusy(v.id); setMsg("");
    try { await activateModelVersion(v.id); await load(); setMsg(`Activado: ${v.filename}`); }
    catch (e: unknown) { setMsg(e instanceof Error ? e.message : "Error al activar"); }
    finally { setBusy(null); }
  };
  const onScan = async () => {
    setBusy("scan"); setMsg("");
    try {
      await scanModels();
      setMsg("Re-escaneo encolado… recarga en unos segundos para ver los modelos registrados.");
    } catch (e: unknown) { setMsg(e instanceof Error ? e.message : "Error al escanear"); }
    finally { setBusy(null); }
  };

  const fmtMetrics = (m?: Record<string, number | null> | null) => {
    if (!m) return "—";
    const parts: string[] = [];
    if (m["mAP50"] != null) parts.push(`mAP50 ${m["mAP50"]}`);
    if (m["mAP50-95"] != null) parts.push(`mAP50-95 ${m["mAP50-95"]}`);
    if (m["epochs"] != null) parts.push(`${m["epochs"]} ep`);
    return parts.length ? parts.join(" · ") : "—";
  };

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto px-4 py-8 space-y-5">
        <Link href="/admin" className="text-sm text-slate-400 hover:text-white flex items-center gap-1">
          <ChevronLeft size={14} /> Admin
        </Link>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Boxes size={22} className="text-blue-400" /> Modelos
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Elige la versión <strong>activa</strong> de cada modelo. Cambiar versión es un clic;
              se aplica en el próximo análisis (sin reconstruir nada). Solo la versión activa se carga.
            </p>
          </div>
          <button onClick={onScan} disabled={busy === "scan"}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm bg-slate-700 hover:bg-slate-600 text-white disabled:opacity-50">
            {busy === "scan" ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            Re-escanear modelos
          </button>
        </div>

        {msg && <div className="text-sm px-4 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-300">{msg}</div>}

        {loading ? (
          <div className="flex justify-center py-16"><Loader2 className="animate-spin text-blue-500" size={28} /></div>
        ) : (
          Object.keys(ROLE_LABELS).map((role) => {
            const versions = roles[role] ?? [];
            return (
              <div key={role} className="bg-slate-800 rounded-xl border border-slate-700">
                <div className="px-4 py-3 border-b border-slate-700 text-sm font-semibold text-white">
                  {ROLE_LABELS[role]} <span className="text-slate-500 font-normal">({versions.length})</span>
                </div>
                {versions.length === 0 ? (
                  <p className="px-4 py-4 text-sm text-slate-500">Sin versiones registradas. Usa «Re-escanear».</p>
                ) : (
                  <ul className="divide-y divide-slate-700/60">
                    {versions.map((v) => (
                      <li key={v.id} className="flex items-center gap-3 px-4 py-3">
                        {v.is_active
                          ? <CheckCircle2 size={18} className="text-emerald-400 shrink-0" />
                          : <Circle size={18} className="text-slate-600 shrink-0" />}
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-white font-mono truncate">{v.filename}</div>
                          <div className="text-xs text-slate-400">
                            <span className="uppercase">{v.source}</span> · {fmtMetrics(v.metrics)}
                          </div>
                        </div>
                        {v.is_active ? (
                          <span className="text-xs px-2 py-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">activo</span>
                        ) : (
                          <button onClick={() => onActivate(v)} disabled={busy === v.id}
                            className={clsx("text-xs px-3 py-1.5 rounded-lg border border-slate-600 text-slate-200 hover:bg-slate-700 disabled:opacity-50")}>
                            {busy === v.id ? "…" : "Activar"}
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })
        )}
      </div>
    </AppShell>
  );
}
