"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import AppShell from "@/components/layout/AppShell";
import { api } from "@/lib/api";
import {
  Download, Film, Loader2, RefreshCw, Monitor, Smartphone,
} from "lucide-react";
import Link from "next/link";
import { clsx } from "clsx";

interface Highlight {
  id: string;
  event_type: string;
  start_s: number;
  end_s: number;
  s3_key?: string;
  clip_url?: string;
  created_at?: string;
  score?: number;
  excitement?: number;
}

const EVENT_LABELS: Record<string, string> = {
  shot_attempt: "Tiro",
  rebound:      "Rebote",
  steal:        "Robo",
  pass:         "Pase",
  default:      "Evento",
};

const EVENT_COLORS: Record<string, string> = {
  shot_attempt: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  rebound:      "bg-blue-500/20 text-blue-400 border-blue-500/30",
  steal:        "bg-purple-500/20 text-purple-400 border-purple-500/30",
  pass:         "bg-green-500/20 text-green-400 border-green-500/30",
  default:      "bg-slate-500/20 text-slate-400 border-slate-500/30",
};

export default function HighlightsPage() {
  const { id: gameId } = useParams<{ id: string }>();
  const [highlights, setHighlights] = useState<Highlight[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [portrait, setPortrait] = useState(false);
  const [filter, setFilter] = useState<string>("all");
  const [genMsg, setGenMsg] = useState<string>("");
  const [genError, setGenError] = useState<string>("");

  const fetchHighlights = async (): Promise<number> => {
    try {
      const { data } = await api.get(`/games/${gameId}/highlights`);
      const list = data ?? [];
      setHighlights(list);
      return list.length;
    } catch {
      setHighlights([]);
      return 0;
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHighlights();
  }, [gameId]);

  const handleGenerate = async () => {
    setGenerating(true);
    setGenError("");
    setGenMsg("");
    const before = highlights.length;
    try {
      const { data } = await api.post(`/games/${gameId}/highlights/generate`, null, { params: { portrait } });
      setGenMsg(`Generando ${data?.events ?? ""} clips… puede tardar 1–3 min.`);
      // Poll until clips appear (the task runs async on the worker).
      const deadline = Date.now() + 4 * 60 * 1000; // 4 min
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 5000));
        const n = await fetchHighlights();
        if (n > before) { setGenMsg(`Listo: ${n} clips generados.`); break; }
      }
      if (Date.now() >= deadline) setGenMsg("Aún procesando… recarga en un momento.");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setGenError(detail ?? (err instanceof Error ? err.message : "No se pudo generar"));
    } finally {
      setGenerating(false);
    }
  };

  const eventTypes = ["all", ...Array.from(new Set(highlights.map(h => h.event_type)))];
  const filtered = filter === "all" ? highlights : highlights.filter(h => h.event_type === filter);

  return (
    <AppShell>
      <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <Link href={`/games/${gameId}`} className="text-sm text-slate-400 hover:text-white mb-2 block">
              ← Volver al partido
            </Link>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Film size={24} className="text-blue-400" />
              Highlights
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Clips generados automáticamente por el motor de visión por computadora.
            </p>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            {/* Portrait/Landscape toggle */}
            <div className="flex items-center gap-1 bg-slate-800 rounded-lg p-1">
              <button
                onClick={() => setPortrait(false)}
                className={clsx(
                  "flex items-center gap-1 px-3 py-1.5 text-sm rounded-md transition-colors",
                  !portrait ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white",
                )}
              >
                <Monitor size={14} /> 16:9
              </button>
              <button
                onClick={() => setPortrait(true)}
                className={clsx(
                  "flex items-center gap-1 px-3 py-1.5 text-sm rounded-md transition-colors",
                  portrait ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white",
                )}
              >
                <Smartphone size={14} /> 9:16
              </button>
            </div>

            <button
              onClick={handleGenerate}
              disabled={generating}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium disabled:opacity-50"
            >
              {generating
                ? <Loader2 size={14} className="animate-spin" />
                : <RefreshCw size={14} />}
              {generating ? "Generando…" : "Generar highlights"}
            </button>
          </div>
        </div>

        {(genMsg || genError) && (
          <div className={clsx(
            "text-sm px-4 py-2 rounded-lg border",
            genError ? "bg-red-900/30 border-red-700/50 text-red-300"
                     : "bg-slate-800 border-slate-700 text-slate-300",
          )}>
            {genError || genMsg}
          </div>
        )}

        {/* Filter tabs */}
        {highlights.length > 0 && (
          <div className="flex gap-2 flex-wrap">
            {eventTypes.map(type => (
              <button
                key={type}
                onClick={() => setFilter(type)}
                className={clsx(
                  "px-3 py-1 text-sm rounded-full border transition-colors",
                  filter === type
                    ? "bg-blue-600 border-blue-500 text-white"
                    : "border-slate-600 text-slate-400 hover:text-white hover:border-slate-400",
                )}
              >
                {type === "all" ? `Todos (${highlights.length})` : `${EVENT_LABELS[type] ?? type} (${highlights.filter(h => h.event_type === type).length})`}
              </button>
            ))}
          </div>
        )}

        {/* Content */}
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="animate-spin text-blue-500" size={32} />
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 gap-4 text-slate-400">
            <Film size={48} className="opacity-30" />
            <p className="text-sm">
              {highlights.length === 0
                ? "Aún no hay highlights. Haz clic en «Generar highlights» para crearlos."
                : "No hay highlights para este filtro."}
            </p>
          </div>
        ) : (
          <div className={clsx(
            "grid gap-4",
            portrait
              ? "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4"
              : "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
          )}>
            {filtered.map((highlight) => (
              <div
                key={highlight.id}
                className="bg-slate-800 rounded-xl overflow-hidden group border border-slate-700 hover:border-slate-500 transition-colors"
              >
                {/* Thumbnail / video preview */}
                <div className={clsx(
                  "relative bg-slate-900 flex items-center justify-center",
                  portrait ? "aspect-[9/16]" : "aspect-video",
                )}>
                  {highlight.clip_url ? (
                    <video
                      src={highlight.clip_url}
                      className="w-full h-full object-contain bg-black"
                      controls
                      playsInline
                      preload="metadata"
                    />
                  ) : (
                    <Film size={32} className="text-slate-600" />
                  )}
                </div>

                {/* Info */}
                <div className="p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className={clsx(
                      "text-xs px-2 py-0.5 rounded-full border",
                      EVENT_COLORS[highlight.event_type] ?? EVENT_COLORS.default,
                    )}>
                      {EVENT_LABELS[highlight.event_type] ?? highlight.event_type}
                    </span>
                    {(highlight.excitement ?? 0) > 0.05 && (
                      <span
                        className="text-xs text-amber-400"
                        title={`Excitación del público: ${Math.round((highlight.excitement ?? 0) * 100)}%`}
                      >
                        {"🔥".repeat(Math.min(3, Math.max(1, Math.ceil((highlight.excitement ?? 0) * 3))))}
                      </span>
                    )}
                    <span className="text-xs text-slate-500">
                      {highlight.start_s.toFixed(1)}s – {highlight.end_s.toFixed(1)}s
                    </span>
                  </div>

                  {highlight.clip_url && (
                    <a
                      href={highlight.clip_url}
                      download
                      className="flex items-center gap-1 text-xs text-slate-400 hover:text-white transition-colors"
                    >
                      <Download size={12} /> Descargar
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
