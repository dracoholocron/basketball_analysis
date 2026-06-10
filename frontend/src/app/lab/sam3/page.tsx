"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { api, sam3Track, sam3Result } from "@/lib/api";
import { ArrowLeft, FlaskConical, Loader2, Play } from "lucide-react";

interface GameOpt { id: string; label: string; }

export default function Sam3LabPage() {
  const [games, setGames] = useState<GameOpt[]>([]);
  const [gameId, setGameId] = useState("");
  const [prompt, setPrompt] = useState("basketball");
  const [startS, setStartS] = useState("");
  const [endS, setEndS] = useState("");
  const [running, setRunning] = useState(false);
  const [state, setState] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [outUrl, setOutUrl] = useState<string | null>(null);
  const [coverage, setCoverage] = useState<number | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api.get("/games", { params: { limit: 100 } })
      .then((r) => {
        const items = r.data?.items ?? r.data ?? [];
        setGames(items.map((g: Record<string, unknown>) => ({
          id: g.id as string,
          label: `${(g.home_team_name as string) ?? "Local"} vs ${(g.away_team_name as string) ?? "Visitante"} · ${String(g.id).slice(0, 8)}`,
        })));
      })
      .catch(() => setGames([]));
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const run = async () => {
    if (!gameId) return;
    setRunning(true); setError(null); setOutUrl(null); setCoverage(null); setState("PENDING");
    try {
      const { task_id } = await sam3Track(gameId, prompt.trim() || "basketball",
        startS.trim() ? Number(startS) : 0, endS.trim() ? Number(endS) : null);
      const deadline = Date.now() + 30 * 60 * 1000;  // 30 min
      pollRef.current = setInterval(async () => {
        try {
          const res = await sam3Result(task_id);
          setState(res.state);
          if (res.state === "SUCCESS") {
            setOutUrl(res.output_url ?? null);
            setCoverage(res.result?.coverage_pct ?? null);
            stop();
          } else if (res.state === "FAILURE" || res.state === "ERROR") {
            setError(res.error ?? "Falló la ejecución"); stop();
          } else if (Date.now() > deadline) {
            setError("Tiempo de espera agotado"); stop();
          }
        } catch (e: unknown) {
          setError(e instanceof Error ? e.message : "Error consultando estado"); stop();
        }
      }, 4000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "No se pudo encolar"); setRunning(false);
    }
  };

  const stop = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    setRunning(false);
  };

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
        <Link href="/" className="text-sm text-slate-400 hover:text-white flex items-center gap-1">
          <ArrowLeft size={14} /> Inicio
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <FlaskConical size={22} className="text-amber-400" /> Piloto SAM 3
            <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30">experimental</span>
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Trackea un objeto por <strong>prompt de texto</strong> (sin clicks) con SAM 3, para comparar
            contra el pipeline de balón con SAM 2. Aislado: no afecta el análisis de producción.
            Requiere el servicio <code>worker-sam3lab</code> levantado y los pesos <code>sam3.pt</code>.
          </p>
        </div>

        <div className="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3">
          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1">Juego (video analizado)</label>
              <select value={gameId} onChange={(e) => setGameId(e.target.value)}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-white text-sm">
                <option value="">— elegir —</option>
                {games.map((g) => <option key={g.id} value={g.id}>{g.label}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Prompt de texto</label>
              <input value={prompt} onChange={(e) => setPrompt(e.target.value)}
                placeholder="basketball"
                className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-white text-sm" />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Inicio (s, opcional)</label>
              <input type="number" min={0} value={startS} onChange={(e) => setStartS(e.target.value)}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-white text-sm" />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Fin (s, opcional)</label>
              <input type="number" min={0} value={endS} onChange={(e) => setEndS(e.target.value)}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-white text-sm" />
            </div>
          </div>
          <button onClick={run} disabled={running || !gameId}
            className="flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm font-medium disabled:opacity-50">
            {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            {running ? `Ejecutando… (${state})` : "Ejecutar SAM 3"}
          </button>
          <p className="text-xs text-slate-500">
            Sugerencia: usa una ventana corta (p.ej. 0–30 s) — SAM 3 es pesado y corre frame a frame.
          </p>
        </div>

        {error && (
          <div className="px-4 py-3 rounded-lg bg-red-900/30 border border-red-700/50 text-sm text-red-300">{error}</div>
        )}

        {(outUrl || coverage != null) && (
          <div className="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3">
            <div className="text-sm text-white">
              Cobertura del objeto: <strong>{coverage != null ? `${coverage}%` : "—"}</strong>
              <span className="text-slate-400"> (frames donde SAM 3 detectó «{prompt}»)</span>
            </div>
            {outUrl && (
              <video src={outUrl} controls playsInline className="w-full rounded-lg bg-black" />
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
