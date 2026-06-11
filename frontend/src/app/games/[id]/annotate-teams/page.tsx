"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import AppShell from "@/components/layout/AppShell";
import VideoControls from "@/components/video/VideoControls";
import {
  getGameVideoUrl, getTeamExemplars, putTeamExemplars,
  type TeamExemplar, type TeamExemplars,
} from "@/lib/api";
import { ChevronLeft, Save, Trash2, Users, Loader2, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { clsx } from "clsx";

const TEAM_COLORS: Record<string, string> = { "1": "#3b82f6", "2": "#ef4444" };

function fmtTime(s: number) {
  if (!isFinite(s)) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export default function AnnotateTeamsPage() {
  const { id: gameId } = useParams<{ id: string }>();
  const router = useRouter();

  const videoRef = useRef<HTMLVideoElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [team, setTeam] = useState<"1" | "2">("1");
  const [exemplars, setExemplars] = useState<TeamExemplars>({ "1": [], "2": [] });
  const [drag, setDrag] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getGameVideoUrl(gameId).then(setVideoUrl).catch(() => null);
    getTeamExemplars(gameId).then((ex) => {
      if (ex) setExemplars({ "1": ex["1"] ?? [], "2": ex["2"] ?? [] });
    });
  }, [gameId]);

  // Mouse → normalized [0..1] coords relative to the rendered video box
  const toNorm = useCallback((clientX: number, clientY: number) => {
    const rect = wrapRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return {
      x: Math.min(1, Math.max(0, (clientX - rect.left) / rect.width)),
      y: Math.min(1, Math.max(0, (clientY - rect.top) / rect.height)),
    };
  }, []);

  function onDown(e: React.MouseEvent) {
    const p = toNorm(e.clientX, e.clientY);
    setDrag({ x0: p.x, y0: p.y, x1: p.x, y1: p.y });
  }
  function onMove(e: React.MouseEvent) {
    if (!drag) return;
    const p = toNorm(e.clientX, e.clientY);
    setDrag({ ...drag, x1: p.x, y1: p.y });
  }
  function onUp() {
    if (!drag) return;
    const x1 = Math.min(drag.x0, drag.x1), y1 = Math.min(drag.y0, drag.y1);
    const x2 = Math.max(drag.x0, drag.x1), y2 = Math.max(drag.y0, drag.y1);
    setDrag(null);
    if (x2 - x1 < 0.02 || y2 - y1 < 0.02) return;  // ignore tiny boxes
    const ex: TeamExemplar = { frame_t: currentTime, bbox_norm: [x1, y1, x2, y2] };
    setExemplars((prev) => ({ ...prev, [team]: [...(prev[team] ?? []), ex] }));
    setSaved(false);
  }

  function removeExemplar(t: string, idx: number) {
    setExemplars((prev) => ({ ...prev, [t]: (prev[t] ?? []).filter((_, i) => i !== idx) }));
    setSaved(false);
  }

  async function save() {
    setSaving(true);
    try {
      await putTeamExemplars(gameId, exemplars);
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }

  function jumpTo(t: number) {
    if (videoRef.current) { videoRef.current.pause(); videoRef.current.currentTime = t; }
  }

  // Boxes drawn on top of the video: in-progress drag + persisted exemplars near now
  const nearby = (exemplars[team] ?? []).map((ex, i) => ({ ex, i }))
    .filter(({ ex }) => Math.abs(ex.frame_t - currentTime) < 0.2);

  return (
    <AppShell title="Anotar equipos" subtitle="Selecciona ejemplos de camiseta por equipo (FashionCLIP)">
      <div className="max-w-4xl mx-auto space-y-4">
        <Link href={`/games/${gameId}`} className="inline-flex items-center gap-1 text-sm text-slate-400 hover:text-white">
          <ChevronLeft size={15} /> Volver al juego
        </Link>

        <div className="bg-slate-800/60 rounded-xl border border-slate-700 px-4 py-3 text-sm text-slate-300">
          Dibuja un recuadro alrededor de uno o más jugadores de cada equipo (mejor con la camiseta bien
          visible). El análisis usará estos ejemplos para asignar equipos por <strong>similitud de imagen</strong>,
          en vez de descripciones de texto. Necesitas ejemplos de <strong>ambos equipos</strong> para activarlo;
          si faltan, se usa el método de texto.
        </div>

        {/* Team selector */}
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-400">Equipo activo:</span>
          {(["1", "2"] as const).map((t) => (
            <button key={t} onClick={() => setTeam(t)}
              className={clsx("px-4 py-1.5 rounded-lg text-sm font-medium border-2 transition-colors",
                team === t ? "text-white" : "text-slate-400 border-transparent bg-slate-700")}
              style={team === t ? { borderColor: TEAM_COLORS[t], background: TEAM_COLORS[t] + "22" } : {}}>
              Equipo {t} · {exemplars[t]?.length ?? 0} ej.
            </button>
          ))}
        </div>

        {/* Video + draw overlay */}
        {videoUrl && (
          <div className="space-y-2">
            <div
              ref={wrapRef}
              className="relative inline-block w-full select-none"
              onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}
            >
              <video
                ref={videoRef}
                src={videoUrl}
                className="w-full rounded-lg bg-black pointer-events-none"
                onLoadedMetadata={() => setDuration(videoRef.current?.duration ?? 0)}
                onTimeUpdate={() => setCurrentTime(videoRef.current?.currentTime ?? 0)}
              />
              {/* persisted boxes near current time */}
              {nearby.map(({ ex, i }) => (
                <div key={i} className="absolute border-2 pointer-events-none"
                  style={{
                    borderColor: TEAM_COLORS[team],
                    left: `${ex.bbox_norm[0] * 100}%`, top: `${ex.bbox_norm[1] * 100}%`,
                    width: `${(ex.bbox_norm[2] - ex.bbox_norm[0]) * 100}%`,
                    height: `${(ex.bbox_norm[3] - ex.bbox_norm[1]) * 100}%`,
                  }} />
              ))}
              {/* drag preview */}
              {drag && (
                <div className="absolute border-2 border-dashed pointer-events-none"
                  style={{
                    borderColor: TEAM_COLORS[team],
                    left: `${Math.min(drag.x0, drag.x1) * 100}%`, top: `${Math.min(drag.y0, drag.y1) * 100}%`,
                    width: `${Math.abs(drag.x1 - drag.x0) * 100}%`, height: `${Math.abs(drag.y1 - drag.y0) * 100}%`,
                  }} />
              )}
            </div>

            <div className="flex items-center gap-3">
              <input type="range" min={0} max={duration || 1} step={0.033} value={currentTime}
                onChange={(e) => jumpTo(Number(e.target.value))}
                className="flex-1 h-1.5 accent-blue-500 cursor-pointer" />
              <span className="text-xs text-slate-400 font-mono shrink-0">{fmtTime(currentTime)} / {fmtTime(duration)}</span>
            </div>
            <VideoControls videoRef={videoRef} />
            <p className="text-xs text-slate-500">
              Pausa en un cuadro claro y arrastra para recuadrar a un jugador del <strong>Equipo {team}</strong>.
            </p>
          </div>
        )}

        {/* Exemplar lists */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {(["1", "2"] as const).map((t) => (
            <div key={t} className="bg-slate-800 rounded-xl border border-slate-700 p-4">
              <div className="flex items-center gap-2 mb-3">
                <Users size={16} style={{ color: TEAM_COLORS[t] }} />
                <h3 className="font-semibold text-white">Equipo {t}</h3>
                <span className="text-xs text-slate-400">({exemplars[t]?.length ?? 0})</span>
              </div>
              {(exemplars[t]?.length ?? 0) === 0 ? (
                <p className="text-xs text-slate-500 py-2">Sin ejemplos aún.</p>
              ) : (
                <ul className="space-y-1.5">
                  {exemplars[t].map((ex, i) => (
                    <li key={i} className="flex items-center justify-between text-sm bg-slate-700/40 rounded px-2 py-1">
                      <button onClick={() => jumpTo(ex.frame_t)} className="text-slate-300 hover:text-white font-mono text-xs">
                        t={fmtTime(ex.frame_t)} · [{ex.bbox_norm.map((n) => n.toFixed(2)).join(", ")}]
                      </button>
                      <button onClick={() => removeExemplar(t, i)} className="text-slate-400 hover:text-red-400">
                        <Trash2 size={14} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>

        <div className="flex items-center justify-end gap-3">
          {saved && <span className="inline-flex items-center gap-1 text-sm text-green-400"><CheckCircle2 size={15} /> Guardado</span>}
          <button onClick={save} disabled={saving}
            className="inline-flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium disabled:opacity-50">
            {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
            Guardar ejemplos
          </button>
        </div>
      </div>
    </AppShell>
  );
}
