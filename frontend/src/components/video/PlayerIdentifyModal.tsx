"use client";

import { useEffect, useRef, useState } from "react";
import { clsx } from "clsx";
import { X } from "lucide-react";
import { COCO_EDGES } from "./LayeredPlayer";
import {
  fetchJobLayersData,
  getPlayerMapping,
  putPlayerMapping,
  type LayersData,
  type Kpt,
  type RosterPlayer,
  type PlayerMapItem,
} from "@/lib/api";

export interface IdentifyTrack {
  track_id: number;
  label: string;
  jersey_number?: string | null;
  team_id?: number | null; // 1 = home, 2 = away
  player_id?: string | null;
}

/**
 * Player-identification popup: plays the RAW video seeked to a frame where the target track is
 * on-screen, looping a short window, and draws ONLY that player's skeleton highlighted (others
 * optionally dimmed). Lets the user correct the dorsal/team and reassign to a roster player —
 * persisted via player-mapping WITHOUT re-running the analysis.
 */
export default function PlayerIdentifyModal({
  jobId,
  gameId,
  track,
  homeTeamName,
  awayTeamName,
  onClose,
  onSaved,
}: {
  jobId: string;
  gameId: string;
  track: IdentifyTrack;
  homeTeamName?: string | null;
  awayTeamName?: string | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [data, setData] = useState<{ raw: string; layers: LayersData } | null>(null);
  const [loadingLayers, setLoadingLayers] = useState(true);
  const [showOthers, setShowOthers] = useState(false);
  const [rosters, setRosters] = useState<{ home: RosterPlayer[]; away: RosterPlayer[] }>({ home: [], away: [] });

  // Correction form state
  const [jersey, setJersey] = useState(track.jersey_number ?? "");
  const [teamId, setTeamId] = useState<number | undefined>(track.team_id ?? undefined);
  const [linkMode, setLinkMode] = useState<"keep" | "existing" | "new">("keep");
  const [playerId, setPlayerId] = useState<string | undefined>(track.player_id ?? undefined);
  const [newName, setNewName] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number | null>(null);

  // Load layers (raw video + poses) and the rosters for reassignment.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [layers, mapping] = await Promise.all([
        fetchJobLayersData(jobId),
        getPlayerMapping(gameId).catch(() => null),
      ]);
      if (cancelled) return;
      if (layers) setData(layers);
      if (mapping) setRosters({ home: mapping.home_roster ?? [], away: mapping.away_roster ?? [] });
      setLoadingLayers(false);
    })();
    return () => { cancelled = true; };
  }, [jobId, gameId]);

  // Seek to where this track is on-screen and loop a short window; draw only its skeleton.
  useEffect(() => {
    const v = videoRef.current, c = canvasRef.current;
    if (!v || !c || !data) return;
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const { layers } = data;
    const fps = layers.fps || 25;
    const tInfo = layers.tracks?.[String(track.track_id)];
    const midFrame = tInfo ? tInfo.mid : 0;
    const span = 3.0; // seconds before/after the representative frame
    const start = Math.max(0, midFrame / fps - span);
    const end = midFrame / fps + span;

    const seek = () => { v.currentTime = start; v.play().catch(() => {}); };
    const onTime = () => { if (v.currentTime >= end || v.currentTime < start - 0.5) v.currentTime = start; };
    v.addEventListener("loadedmetadata", seek);
    v.addEventListener("timeupdate", onTime);
    if (v.readyState >= 1) seek();

    const drawSkeleton = (kp: Kpt[], sx: number, sy: number, stroke: string, fill: string, lw: number, dot: number) => {
      if (!kp || kp.length < 17) return;
      ctx.lineWidth = lw; ctx.strokeStyle = stroke; ctx.fillStyle = fill;
      for (const [a, b] of COCO_EDGES) {
        if (kp[a][2] > 0.3 && kp[b][2] > 0.3) {
          ctx.beginPath(); ctx.moveTo(kp[a][0] * sx, kp[a][1] * sy);
          ctx.lineTo(kp[b][0] * sx, kp[b][1] * sy); ctx.stroke();
        }
      }
      for (const p of kp) {
        if (p[2] > 0.3) { ctx.beginPath(); ctx.arc(p[0] * sx, p[1] * sy, dot, 0, 6.28); ctx.fill(); }
      }
    };

    const draw = () => {
      const dw = v.clientWidth, dh = v.clientHeight;
      if (c.width !== dw || c.height !== dh) { c.width = dw; c.height = dh; }
      ctx.clearRect(0, 0, dw, dh);
      const sx = dw / (layers.width || dw), sy = dh / (layers.height || dh);
      const f = Math.round(v.currentTime * fps);
      const frame = layers.poses?.[String(f)] as Record<string, Kpt[]> | undefined;
      if (frame && !Array.isArray(frame)) {
        // Dimmed context players (optional)
        if (showOthers) {
          for (const [tid, kp] of Object.entries(frame)) {
            if (Number(tid) === track.track_id) continue;
            drawSkeleton(kp, sx, sy, "rgba(148,163,184,0.35)", "rgba(148,163,184,0.35)", 1.5, 2);
          }
        }
        // The target player: bright highlight + halo
        const me = frame[String(track.track_id)];
        if (me && me.length >= 17) {
          // halo: a translucent disc around the player's torso center
          const cx = ((me[5]?.[0] ?? 0) + (me[6]?.[0] ?? 0) + (me[11]?.[0] ?? 0) + (me[12]?.[0] ?? 0)) / 4;
          const cy = ((me[5]?.[1] ?? 0) + (me[6]?.[1] ?? 0) + (me[11]?.[1] ?? 0) + (me[12]?.[1] ?? 0)) / 4;
          ctx.beginPath(); ctx.fillStyle = "rgba(250,204,21,0.12)";
          ctx.arc(cx * sx, cy * sy, 46, 0, 6.28); ctx.fill();
          drawSkeleton(me, sx, sy, "rgba(250,204,21,0.98)", "rgba(255,255,255,0.98)", 3, 4);
        }
      }
      rafRef.current = requestAnimationFrame(draw);
    };
    rafRef.current = requestAnimationFrame(draw);

    return () => {
      v.removeEventListener("loadedmetadata", seek);
      v.removeEventListener("timeupdate", onTime);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [data, showOthers, track.track_id]);

  async function save() {
    setSaving(true);
    setErr(null);
    try {
      const item: PlayerMapItem = { track_id: track.track_id };
      const jn = jersey.trim();
      if (jn !== (track.jersey_number ?? "")) item.jersey_number = jn;
      if (teamId && teamId !== track.team_id) item.team_id = teamId;

      if (linkMode === "existing") {
        item.player_id = playerId ?? null; // may unlink if cleared
      } else if (linkMode === "new") {
        if (!newName.trim()) { setErr("Escribe el nombre del jugador nuevo."); setSaving(false); return; }
        item.new_player_name = newName.trim();
        item.team_id = teamId ?? track.team_id ?? undefined as unknown as number;
        item.jersey_number = jn || track.jersey_number || undefined as unknown as string;
      } else {
        // keep: preserve the existing link while correcting number/team only
        item.player_id = track.player_id ?? null;
      }
      await putPlayerMapping(gameId, [item]);
      onSaved();
    } catch {
      setErr("No se pudo guardar. Revisa tu sesión e inténtalo de nuevo.");
    } finally {
      setSaving(false);
    }
  }

  const roster = (teamId === 2 ? rosters.away : rosters.home);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="bg-slate-800 border border-slate-700 rounded-2xl max-w-3xl w-full shadow-2xl max-h-[92vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-700">
          <h3 className="font-semibold text-white text-sm">
            Identificar jugador · <span className="font-mono text-amber-300">{track.label}</span>
            <span className="text-slate-500"> (track #{track.track_id})</span>
          </h3>
          <button onClick={onClose}><X size={18} className="text-slate-400 hover:text-white" /></button>
        </div>

        <div className="p-5 space-y-4">
          {/* Video + isolated skeleton overlay */}
          {loadingLayers ? (
            <div className="h-48 flex items-center justify-center text-sm text-slate-400">Cargando capas…</div>
          ) : data ? (
            <>
              <div className="relative inline-block w-full">
                <video ref={videoRef} src={data.raw} muted loop playsInline className="w-full rounded-lg bg-black" />
                <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none" />
              </div>
              {!data.layers.tracks && (
                <div className="rounded-lg border border-amber-600/40 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-200">
                  Este análisis es anterior al resaltado por jugador. Vuelve a analizar con “Capas de video”
                  activadas para ver solo a este jugador pintado. La corrección de dorsal/equipo funciona igual.
                </div>
              )}
              <div className="flex items-center gap-2 text-xs">
                <span className="text-slate-400">Solo se resalta el jugador seleccionado.</span>
                <button onClick={() => setShowOthers(v => !v)}
                  className={clsx("px-2.5 py-1 rounded-md transition-colors ml-auto",
                    showOthers ? "bg-slate-600 text-white" : "bg-slate-700 text-slate-400")}>
                  {showOthers ? "Ocultar otros" : "Mostrar otros (atenuados)"}
                </button>
              </div>
            </>
          ) : (
            <div className="rounded-lg border border-amber-600/40 bg-amber-500/10 px-4 py-3 text-xs text-amber-200">
              Este análisis no tiene capas de video. Vuelve a analizar con <b>“Capas de video”</b> activadas
              para ver al jugador resaltado. Aún puedes corregir el dorsal y reasignarlo abajo.
            </div>
          )}

          {/* Correction form */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400">Dorsal (número)</label>
              <input value={jersey} onChange={e => setJersey(e.target.value)} placeholder="p. ej. 23"
                className="w-full mt-1 bg-slate-700 text-white text-sm rounded-lg px-3 py-2" />
            </div>
            <div>
              <label className="text-xs text-slate-400">Equipo</label>
              <select value={teamId ?? ""} onChange={e => { setTeamId(e.target.value ? Number(e.target.value) : undefined); setPlayerId(undefined); }}
                className="w-full mt-1 bg-slate-700 text-white text-sm rounded-lg px-3 py-2">
                <option value="">— sin asignar —</option>
                <option value={1}>{homeTeamName ?? "Local"}</option>
                <option value={2}>{awayTeamName ?? "Visitante"}</option>
              </select>
            </div>
          </div>

          <div>
            <label className="text-xs text-slate-400">Vincular a jugador del roster</label>
            <div className="mt-1 flex flex-wrap gap-2 text-xs">
              {([["keep", "Mantener vínculo"], ["existing", "Jugador existente"], ["new", "Crear nuevo"]] as const).map(([m, lbl]) => (
                <button key={m} onClick={() => setLinkMode(m)}
                  className={clsx("px-3 py-1.5 rounded-lg border transition-colors",
                    linkMode === m ? "bg-emerald-600 border-emerald-500 text-white" : "border-slate-600 text-slate-300 hover:border-slate-400")}>
                  {lbl}
                </button>
              ))}
            </div>
            {linkMode === "existing" && (
              <select value={playerId ?? ""} onChange={e => setPlayerId(e.target.value || undefined)}
                className="w-full mt-2 bg-slate-700 text-white text-sm rounded-lg px-3 py-2">
                <option value="">— sin vincular —</option>
                {roster.map(p => (
                  <option key={p.id} value={p.id}>{p.name}{p.jersey_number ? ` (#${p.jersey_number})` : ""}</option>
                ))}
                {roster.length === 0 && <option disabled>No hay roster cargado para este equipo</option>}
              </select>
            )}
            {linkMode === "new" && (
              <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Nombre del jugador nuevo"
                className="w-full mt-2 bg-slate-700 text-white text-sm rounded-lg px-3 py-2" />
            )}
          </div>

          {err && <p className="text-xs text-red-400">{err}</p>}

          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="px-3 py-2 text-sm text-slate-300 hover:text-white">Cancelar</button>
            <button onClick={save} disabled={saving}
              className="px-4 py-2 text-sm rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white disabled:opacity-50">
              {saving ? "Guardando…" : "Guardar identificación"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
