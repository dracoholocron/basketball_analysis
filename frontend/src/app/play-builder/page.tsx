"use client";

export const dynamic = "force-dynamic";

import React, { useState, useRef, useCallback, useEffect, useReducer } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import AppShell from "@/components/layout/AppShell";
import { listPlays, createPlay, updatePlay, getPlay } from "@/lib/api";
import {
  Save, Download, Move, Share2, Check, Plus, Trash2, Play as PlayIcon,
  ChevronDown, ChevronUp, Upload, Undo2, Redo2, SlidersHorizontal, Pencil,
} from "lucide-react";
import { ArrowRight as Arrow } from "lucide-react";
import { clsx } from "clsx";
import { api } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

interface PlayEntry {
  id: string; name: string; category: string; description?: string;
  is_template: boolean; tags?: string[]; pace?: string;
}

const PLAYER_COLORS = ["#2563eb", "#7c3aed", "#16a34a", "#d97706", "#dc2626"];
const OPP_COLOR = "#ef4444";
const POSITIONS = ["PG", "SG", "SF", "PF", "C"];

interface PlayerNode { id: string; x: number; y: number; label: string; color: string; team: 1 | 2; }
interface ArrowShape { id: string; x1: number; y1: number; x2: number; y2: number; style: "pass" | "cut" | "dribble" | "screen"; }
interface FreeformPath { id: string; d: string; color: string; }

interface FrameData {
  index: number;
  players: PlayerNode[];
  arrows: ArrowShape[];
  freeform_paths: FreeformPath[];
  notes: string;
}

type CanvasState = { players: PlayerNode[]; arrows: ArrowShape[]; freeform_paths: FreeformPath[] };

// ─── Undo/Redo reducer ────────────────────────────────────────────────────────

interface UndoState { past: CanvasState[]; present: CanvasState; future: CanvasState[]; }

type UndoAction =
  | { type: "SET"; state: CanvasState }
  | { type: "UNDO" }
  | { type: "REDO" };

function undoReducer(state: UndoState, action: UndoAction): UndoState {
  switch (action.type) {
    case "SET": {
      return { past: [...state.past.slice(-30), state.present], present: action.state, future: [] };
    }
    case "UNDO": {
      if (state.past.length === 0) return state;
      const prev = state.past[state.past.length - 1];
      return { past: state.past.slice(0, -1), present: prev, future: [state.present, ...state.future] };
    }
    case "REDO": {
      if (state.future.length === 0) return state;
      const next = state.future[0];
      return { past: [...state.past, state.present], present: next, future: state.future.slice(1) };
    }
  }
}

// ─── Arrow styles ─────────────────────────────────────────────────────────────

const ARROW_STYLES: Record<string, { dash?: string; color: string; label: string }> = {
  pass:    { color: "#2563eb", label: "Pass" },
  cut:     { dash: "6 4", color: "#7c3aed", label: "Cut" },
  dribble: { dash: "2 4", color: "#16a34a", label: "Dribble" },
  screen:  { color: "#d97706", label: "Screen" },
};

// ─── CourtCanvas ──────────────────────────────────────────────────────────────

function CourtCanvas({
  frame, onUpdate, tool, arrowStyle, svgRef: externalRef, animating,
}: {
  frame: CanvasState;
  onUpdate: (s: CanvasState) => void;
  tool: "select" | "arrow" | "freedraw" | "player" | "opponent";
  arrowStyle: keyof typeof ARROW_STYLES;
  svgRef?: React.RefObject<SVGSVGElement | null>;
  animating?: boolean;
}) {
  const internalRef = useRef<SVGSVGElement>(null);
  const svgRef = (externalRef ?? internalRef) as React.RefObject<SVGSVGElement>;
  const [dragging, setDragging] = useState<string | null>(null);
  const [arrowStart, setArrowStart] = useState<{ x: number; y: number } | null>(null);
  const [freePath, setFreePath] = useState<string | null>(null);
  const [freePoints, setFreePoints] = useState<{ x: number; y: number }[]>([]);

  function getSVGCoords(e: React.MouseEvent): { x: number; y: number } {
    const rect = svgRef.current!.getBoundingClientRect();
    return { x: ((e.clientX - rect.left) / rect.width) * 500, y: ((e.clientY - rect.top) / rect.height) * 280 };
  }

  function onMouseDown(e: React.MouseEvent) {
    if (tool === "arrow") { setArrowStart(getSVGCoords(e)); }
    if (tool === "freedraw") { const pt = getSVGCoords(e); setFreePoints([pt]); setFreePath(`M ${pt.x} ${pt.y}`); }
    if (tool === "player" || tool === "opponent") {
      const pt = getSVGCoords(e);
      const team: 1 | 2 = tool === "player" ? 1 : 2;
      const ownCount = frame.players.filter(p => p.team === 1).length;
      const oppCount = frame.players.filter(p => p.team === 2).length;
      // A1: use position names for team 1, numbers for opponents
      const label = team === 1 ? (POSITIONS[ownCount] ?? String(ownCount + 1)) : String(oppCount + 1);
      const color = team === 1 ? PLAYER_COLORS[ownCount % 5] : OPP_COLOR;
      const newPlayer: PlayerNode = { id: Math.random().toString(36).slice(2), x: pt.x, y: pt.y, label, color, team };
      onUpdate({ ...frame, players: [...frame.players, newPlayer] });
    }
  }

  function onMouseMove(e: React.MouseEvent) {
    if (dragging) {
      const pt = getSVGCoords(e);
      onUpdate({ ...frame, players: frame.players.map(p => p.id === dragging ? { ...p, x: pt.x, y: pt.y } : p) });
    }
    if (tool === "freedraw" && freePoints.length > 0) {
      const pt = getSVGCoords(e);
      const pts = [...freePoints, pt];
      setFreePoints(pts);
      setFreePath("M " + pts.map(p => `${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" L "));
    }
  }

  function onMouseUp(e: React.MouseEvent) {
    if (tool === "arrow" && arrowStart) {
      const pt = getSVGCoords(e);
      if (Math.hypot(pt.x - arrowStart.x, pt.y - arrowStart.y) > 12) {
        onUpdate({ ...frame, arrows: [...frame.arrows, { id: Math.random().toString(36).slice(2), x1: arrowStart.x, y1: arrowStart.y, x2: pt.x, y2: pt.y, style: arrowStyle as ArrowShape["style"] }] });
      }
      setArrowStart(null);
    }
    if (tool === "freedraw" && freePath && freePoints.length > 2) {
      onUpdate({ ...frame, freeform_paths: [...frame.freeform_paths, { id: Math.random().toString(36).slice(2), d: freePath, color: "#1e293b" }] });
      setFreePath(null); setFreePoints([]);
    }
    setDragging(null);
  }

  return (
    <svg ref={svgRef} viewBox="0 0 500 280"
      className={clsx("w-full border border-slate-200 rounded-xl select-none", animating && "transition-all duration-700")}
      style={{ cursor: tool === "arrow" || tool === "freedraw" ? "crosshair" : tool === "player" || tool === "opponent" ? "copy" : "default" }}
      onMouseDown={onMouseDown} onMouseUp={onMouseUp} onMouseMove={onMouseMove}
    >
      <defs>
        {Object.entries(ARROW_STYLES).map(([key, s]) => (
          <marker key={key} id={`arrowhead-${key}`} markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill={s.color} />
          </marker>
        ))}
      </defs>
      {/* Court surface */}
      <rect width="500" height="280" fill="#c8a96e" rx="8" />
      <rect x="2" y="2" width="496" height="276" fill="none" stroke="#f5f0e8" strokeWidth="2" rx="6" />
      <circle cx="250" cy="140" r="28" fill="none" stroke="#f5f0e8" strokeWidth="1.5" />
      <line x1="250" y1="2" x2="250" y2="278" stroke="#f5f0e8" strokeWidth="1.5" />
      <rect x="2" y="89" width="95" height="102" fill="none" stroke="#f5f0e8" strokeWidth="1.5" />
      <path d="M 97 110 A 30 30 0 0 1 97 170" fill="none" stroke="#f5f0e8" strokeWidth="1.5" />
      <rect x="403" y="89" width="95" height="102" fill="none" stroke="#f5f0e8" strokeWidth="1.5" />
      <path d="M 403 110 A 30 30 0 0 0 403 170" fill="none" stroke="#f5f0e8" strokeWidth="1.5" />
      <circle cx="15" cy="140" r="6" fill="none" stroke="#f5f0e8" strokeWidth="2" />
      <circle cx="485" cy="140" r="6" fill="none" stroke="#f5f0e8" strokeWidth="2" />
      <path d="M 2 55 L 95 55 A 120 120 0 0 1 95 225 L 2 225" fill="none" stroke="#f5f0e8" strokeWidth="1.5" />
      <path d="M 498 55 L 405 55 A 120 120 0 0 0 405 225 L 498 225" fill="none" stroke="#f5f0e8" strokeWidth="1.5" />

      {/* Freeform paths */}
      {frame.freeform_paths.map(fp => (
        <path key={fp.id} d={fp.d} fill="none" stroke={fp.color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      ))}
      {freePath && <path d={freePath} fill="none" stroke="#1e293b" strokeWidth="2" strokeOpacity="0.5" strokeLinecap="round" />}

      {/* Arrows */}
      {frame.arrows.map((a) => {
        const s = ARROW_STYLES[a.style] || ARROW_STYLES.pass;
        return (
          <line key={a.id} x1={a.x1} y1={a.y1} x2={a.x2} y2={a.y2}
            stroke={s.color} strokeWidth="2.5" strokeDasharray={s.dash}
            markerEnd={`url(#arrowhead-${a.style})`} />
        );
      })}
      {arrowStart && <circle cx={arrowStart.x} cy={arrowStart.y} r="4" fill="#2563eb" opacity="0.5" />}

      {/* Players — A1: position label above circle */}
      {frame.players.map((p) => (
        <g key={p.id} transform={`translate(${p.x},${p.y})`}
          style={{ cursor: tool === "select" ? "grab" : "default" }}
          onMouseDown={(e) => { if (tool === "select") { e.stopPropagation(); setDragging(p.id); } }}>
          {/* A1: position label floating above the circle */}
          <text y="-24" textAnchor="middle" fill="#1e293b" fontSize="9" fontWeight="800"
            style={{ textShadow: "0 1px 2px rgba(255,255,255,0.8)", userSelect: "none" }}>
            {p.team === 1 ? p.label : ""}
          </text>
          <circle r="16" fill={p.color} stroke="white" strokeWidth="2.5" />
          <text textAnchor="middle" dominantBaseline="middle" fill="white" fontSize="11" fontWeight="700"
            style={{ userSelect: "none" }}>
            {p.label}
          </text>
        </g>
      ))}
    </svg>
  );
}

// ─── Mini court for frame thumbnails (A3) ─────────────────────────────────────

function MiniCourt({ frame }: { frame: FrameData }) {
  return (
    <svg viewBox="0 0 500 280" className="w-full rounded border border-slate-200" style={{ height: 90 }}>
      <rect width="500" height="280" fill="#c8a96e" rx="4" />
      <line x1="250" y1="0" x2="250" y2="280" stroke="#f5f0e8" strokeWidth="1.5" />
      <circle cx="250" cy="140" r="28" fill="none" stroke="#f5f0e8" strokeWidth="1.5" />
      <rect x="2" y="89" width="95" height="102" fill="none" stroke="#f5f0e8" strokeWidth="1.5" />
      <rect x="403" y="89" width="95" height="102" fill="none" stroke="#f5f0e8" strokeWidth="1.5" />
      {/* Arrows */}
      {frame.arrows.map((a) => {
        const s = ARROW_STYLES[a.style] || ARROW_STYLES.pass;
        return <line key={a.id} x1={a.x1} y1={a.y1} x2={a.x2} y2={a.y2}
          stroke={s.color} strokeWidth="3" strokeDasharray={s.dash} />;
      })}
      {/* Players */}
      {frame.players.map((p) => (
        <g key={p.id} transform={`translate(${p.x},${p.y})`}>
          <circle r="16" fill={p.color} stroke="white" strokeWidth="2" />
          <text textAnchor="middle" dominantBaseline="middle" fill="white" fontSize="11" fontWeight="700">{p.label}</text>
        </g>
      ))}
    </svg>
  );
}

// ─── Default frame ────────────────────────────────────────────────────────────

// A1: default players now use position labels instead of numbers
const DEFAULT_FRAME: FrameData = {
  index: 0,
  players: [
    { id: "p1", x: 100, y: 140, label: "PG", color: PLAYER_COLORS[0], team: 1 },
    { id: "p2", x: 180, y: 80,  label: "SG", color: PLAYER_COLORS[1], team: 1 },
    { id: "p3", x: 180, y: 200, label: "SF", color: PLAYER_COLORS[2], team: 1 },
    { id: "p4", x: 250, y: 60,  label: "PF", color: PLAYER_COLORS[3], team: 1 },
    { id: "p5", x: 250, y: 220, label: "C",  color: PLAYER_COLORS[4], team: 1 },
  ],
  arrows: [],
  freeform_paths: [],
  notes: "",
};

function emptyFrame(index: number): FrameData {
  return { ...DEFAULT_FRAME, index, players: DEFAULT_FRAME.players.map(p => ({ ...p })), arrows: [], freeform_paths: [], notes: "" };
}

// ─── PlayBuilderContent ───────────────────────────────────────────────────────

function PlayBuilderContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const svgRef = useRef<SVGSVGElement | null>(null);

  const [plays, setPlays] = useState<PlayEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingPlay, setSavingPlay] = useState(false);
  const [copied, setCopied] = useState(false);
  const [currentPlayId, setCurrentPlayId] = useState<string | null>(null);
  const [playName, setPlayName] = useState("New Play");

  // Frames
  const [frames, setFrames] = useState<FrameData[]>([DEFAULT_FRAME]);
  const [currentFrameIdx, setCurrentFrameIdx] = useState(0);
  const [animating, setAnimating] = useState(false);
  const animRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Undo/Redo
  const [undoState, dispatchUndo] = useReducer(undoReducer, {
    past: [],
    present: { players: DEFAULT_FRAME.players, arrows: [], freeform_paths: [] },
    future: [],
  });

  // Tools (A2: now controls the vertical panel)
  const [tool, setTool] = useState<"select" | "arrow" | "freedraw" | "player" | "opponent">("select");
  const [arrowStyle, setArrowStyle] = useState<keyof typeof ARROW_STYLES>("pass");
  const [showArrowMenu, setShowArrowMenu] = useState(false);

  // Filters
  const [showFilters, setShowFilters] = useState(false);
  const [filterType, setFilterType] = useState("all");
  const [filterPace, setFilterPace] = useState("all");
  const [filterTag, setFilterTag] = useState("all");

  useEffect(() => {
    const encoded = searchParams.get("play");
    if (encoded) {
      try {
        const decoded = JSON.parse(atob(encoded));
        if (decoded.frames) { setFrames(decoded.frames); setCurrentFrameIdx(0); }
        else if (decoded.players) {
          setFrames([{ ...DEFAULT_FRAME, players: decoded.players, arrows: decoded.arrows ?? [] }]);
        }
        if (decoded.name) setPlayName(decoded.name);
      } catch { /* ignore */ }
    }
    listPlays()
      .then((d) => setPlays(d.items ?? d))
      .catch(() => router.replace("/login"))
      .finally(() => setLoading(false));
  }, [router, searchParams]);

  const currentFrame = frames[currentFrameIdx] ?? DEFAULT_FRAME;

  function updateCurrentFrame(state: CanvasState) {
    dispatchUndo({ type: "SET", state });
    setFrames(prev => prev.map((f, i) => i === currentFrameIdx ? { ...f, ...state } : f));
  }

  function undo() {
    dispatchUndo({ type: "UNDO" });
    setFrames(prev => prev.map((f, i) => i === currentFrameIdx ? { ...f, ...undoState.past[undoState.past.length - 1] } : f));
  }

  function redo() {
    dispatchUndo({ type: "REDO" });
    setFrames(prev => prev.map((f, i) => i === currentFrameIdx ? { ...f, ...undoState.future[0] } : f));
  }

  function addFrame(empty = false) {
    const newFrame = empty ? emptyFrame(frames.length) : { ...currentFrame, index: frames.length, notes: "", arrows: [], freeform_paths: [] };
    setFrames(prev => [...prev, newFrame]);
    setCurrentFrameIdx(frames.length);
  }

  function deleteFrame(idx: number) {
    if (frames.length <= 1) return;
    const next = frames.filter((_, i) => i !== idx).map((f, i) => ({ ...f, index: i }));
    setFrames(next);
    setCurrentFrameIdx(Math.min(idx, next.length - 1));
  }

  function playAnimation() {
    if (frames.length <= 1) return;
    setAnimating(true);
    let i = 0;
    animRef.current = setInterval(() => {
      i++;
      if (i >= frames.length) { clearInterval(animRef.current!); setAnimating(false); setCurrentFrameIdx(0); return; }
      setCurrentFrameIdx(i);
    }, 1500);
  }

  function quickAddTeam(team: 1 | 2) {
    const positions: Array<{x: number; y: number}> = [
      { x: 100, y: 140 }, { x: 180, y: 80 }, { x: 180, y: 200 }, { x: 250, y: 60 }, { x: 250, y: 220 }
    ];
    const players: PlayerNode[] = positions.map((pos, i) => ({
      id: `${team === 1 ? "p" : "d"}${i + 1}-${Date.now()}`,
      x: pos.x + (team === 2 ? 150 : 0),
      y: pos.y,
      // A1: team 1 gets position labels; team 2 gets numbers
      label: team === 1 ? POSITIONS[i] : String(i + 1),
      color: team === 1 ? PLAYER_COLORS[i % 5] : OPP_COLOR,
      team,
    }));
    const existing = currentFrame.players.filter(p => p.team !== team);
    updateCurrentFrame({ ...currentFrame, players: [...existing, ...players] });
  }

  function clearCanvas() {
    updateCurrentFrame({ players: DEFAULT_FRAME.players.map(p => ({ ...p })), arrows: [], freeform_paths: [] });
  }

  async function savePlay() {
    setSavingPlay(true);
    try {
      const svgData = {
        version: 2,
        frames: frames.map(f => ({
          index: f.index, players: f.players, arrows: f.arrows,
          freeform_paths: f.freeform_paths, notes: f.notes,
        })),
      };
      if (currentPlayId) {
        await updatePlay(currentPlayId, { name: playName, svg_data: svgData, svg_data_version: 2 });
      } else {
        const created = await createPlay({ name: playName, category: "quick_hitter", svg_data: svgData, svg_data_version: 2 });
        setCurrentPlayId(created.id);
        setPlays(prev => [created, ...prev]);
      }
    } catch (err) { console.error(err); }
    finally { setSavingPlay(false); }
  }

  async function loadPlay(play: PlayEntry) {
    setPlayName(play.name);
    setCurrentPlayId(play.id);
    try {
      const full = await getPlay(play.id);
      const svg = full.svg_data;
      if (svg?.version === 2 && Array.isArray(svg.frames)) {
        setFrames(svg.frames as FrameData[]);
        setCurrentFrameIdx(0);
      } else if (svg?.players) {
        setFrames([{ index: 0, players: svg.players as PlayerNode[], arrows: svg.arrows ?? [], freeform_paths: [], notes: "" }]);
        setCurrentFrameIdx(0);
      } else {
        setFrames([DEFAULT_FRAME]);
      }
    } catch {
      setFrames([DEFAULT_FRAME]);
    }
  }

  async function exportPDF() {
    const svg = svgRef.current;
    if (!svg) return;
    const svgData = new XMLSerializer().serializeToString(svg);
    const blob = new Blob([svgData], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = async () => {
      const canvas = document.createElement("canvas");
      canvas.width = 1000; canvas.height = 560;
      canvas.getContext("2d")?.drawImage(img, 0, 0, 1000, 560);
      URL.revokeObjectURL(url);
      const pngDataUrl = canvas.toDataURL("image/png");
      const { jsPDF } = await import("jspdf");
      const doc = new jsPDF({ orientation: "landscape", unit: "px", format: [1000, 600] });
      if (frames.length <= 4) {
        frames.forEach((_, i) => {
          if (i > 0) doc.addPage();
          doc.addImage(pngDataUrl, "PNG", 0, 0, 1000, 560);
          doc.setFontSize(12); doc.text(`${playName} — Frame ${i + 1}/${frames.length}`, 20, 580);
        });
      } else {
        doc.addImage(pngDataUrl, "PNG", 0, 0, 1000, 560);
        doc.text(playName, 20, 580);
      }
      doc.save(`${playName.replace(/\s+/g, "_")}.pdf`);
    };
    img.src = url;
  }

  function shareURL() {
    const payload = { name: playName, frames };
    const encoded = btoa(JSON.stringify(payload));
    const url = `${window.location.origin}${window.location.pathname}?play=${encoded}`;
    navigator.clipboard.writeText(url).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2500); });
  }

  async function handleImportPDF(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    try {
      const { data } = await api.post("/plays/import-pdf", form, { headers: { "Content-Type": "multipart/form-data" } });
      setPlays(prev => [data, ...prev]);
      setPlayName(data.name);
      setCurrentPlayId(data.id);
    } catch (err) { console.error(err); }
    e.target.value = "";
  }

  const filteredPlays = plays.filter(p => {
    if (filterType !== "all" && p.category !== filterType) return false;
    if (filterPace !== "all" && p.pace !== filterPace) return false;
    if (filterTag !== "all" && !(p.tags ?? []).includes(filterTag)) return false;
    return true;
  });
  const allTags = Array.from(new Set(plays.flatMap(p => p.tags ?? [])));

  // A2: vertical tool panel items
  const TOOL_ITEMS = [
    { id: "select" as const, icon: <Move size={14} />, label: "Select" },
    { id: "player" as const, icon: <span className="text-[11px] font-bold text-blue-600">T</span>, label: "Team" },
    { id: "opponent" as const, icon: <span className="text-[11px] font-bold text-red-500">O</span>, label: "Opp" },
    { id: "freedraw" as const, icon: <Pencil size={14} />, label: "Draw" },
  ];

  return (
    <AppShell title="Play Builder" subtitle="Design and organize your playbook">
      <div className="flex gap-4 max-w-[1400px] mx-auto">

        {/* ── Library Panel ──────────────────────────────────────────────────── */}
        <div className="w-60 flex-shrink-0 space-y-3">
          <label className="btn-secondary btn-sm w-full flex items-center gap-2 cursor-pointer">
            <Upload size={13} /> Import PDF
            <input type="file" accept=".pdf" className="sr-only" onChange={handleImportPDF} />
          </label>

          <button onClick={() => setShowFilters(v => !v)} className="btn-ghost btn-sm w-full flex items-center justify-between">
            <span className="flex items-center gap-1.5"><SlidersHorizontal size={13} />Filters</span>
            {showFilters ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>

          {showFilters && (
            <div className="card p-3 space-y-2">
              {[
                { label: "Type", value: filterType, onChange: setFilterType, options: [["all","All types"],["set_play","Set Play"],["system","System"],["inbound","Inbound"],["imported","Imported"]] },
                { label: "Pace", value: filterPace, onChange: setFilterPace, options: [["all","All paces"],["slow","Slow"],["slow-to-medium","Slow-Med"],["medium","Medium"],["medium-to-fast","Med-Fast"],["fast","Fast"]] },
              ].map(({ label, value, onChange, options }) => (
                <div key={label}>
                  <p className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">{label}</p>
                  <select className="input text-xs w-full py-1" value={value} onChange={e => onChange(e.target.value)}>
                    {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
              ))}
              {allTags.length > 0 && (
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">Tag</p>
                  <select className="input text-xs w-full py-1" value={filterTag} onChange={e => setFilterTag(e.target.value)}>
                    <option value="all">All tags</option>
                    {allTags.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
              )}
            </div>
          )}

          <div className="card p-0 overflow-hidden">
            <div className="px-3 py-2.5 border-b border-slate-50">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                Playbook ({filteredPlays.length})
              </p>
            </div>
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <div className="h-4 w-4 rounded-full border-2 border-primary-200 border-t-primary-600 animate-spin" />
              </div>
            ) : (
              <div className="divide-y divide-slate-50 max-h-[500px] overflow-y-auto">
                {filteredPlays.map((p) => (
                  <button key={p.id} onClick={() => loadPlay(p)}
                    className={clsx("w-full text-left px-3 py-2.5 hover:bg-slate-50 transition-colors", currentPlayId === p.id && "bg-indigo-50")}>
                    <p className="text-xs font-medium text-slate-700 truncate">{p.name}</p>
                    <div className="flex flex-wrap gap-1 mt-0.5">
                      {p.is_template && <span className="text-[9px] text-violet-500 font-semibold">Template</span>}
                      {p.pace && <span className="text-[9px] text-slate-400">{p.pace}</span>}
                      {(p.tags ?? []).slice(0, 2).map(t => (
                        <span key={t} className="text-[9px] bg-slate-100 text-slate-500 px-1 rounded">{t}</span>
                      ))}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── Canvas Column ───────────────────────────────────────────────────── */}
        <div className="flex-1 space-y-3 min-w-0">

          {/* Top action bar (simplified — tools moved to vertical panel) */}
          <div className="card py-2.5 px-4 flex items-center gap-2 flex-wrap">
            <input
              aria-label="Play name"
              className="input max-w-xs text-sm font-semibold"
              value={playName}
              onChange={e => setPlayName(e.target.value)}
            />
            <button onClick={undo} disabled={undoState.past.length === 0} className="btn-ghost btn-sm" title="Undo">
              <Undo2 size={13} />
            </button>
            <button onClick={redo} disabled={undoState.future.length === 0} className="btn-ghost btn-sm" title="Redo">
              <Redo2 size={13} />
            </button>
            <button onClick={() => quickAddTeam(1)} className="btn-ghost btn-sm text-blue-600 text-xs">+Team</button>
            <button onClick={() => quickAddTeam(2)} className="btn-ghost btn-sm text-red-500 text-xs">+Opp</button>
            <button onClick={clearCanvas} className="btn-ghost btn-sm"><Trash2 size={13} /> Reset</button>
            <div className="ml-auto flex items-center gap-2">
              <button onClick={() => playAnimation()} disabled={animating || frames.length <= 1} className="btn-secondary btn-sm">
                <PlayIcon size={13} /> Play
              </button>
              <button onClick={exportPDF} className="btn-secondary btn-sm"><Download size={13} /> PDF</button>
              <button onClick={shareURL} className="btn-secondary btn-sm">
                {copied ? <Check size={13} className="text-green-600" /> : <Share2 size={13} />}
                {copied ? "Copied!" : "Share"}
              </button>
              <button onClick={savePlay} disabled={savingPlay} className="btn-primary btn-sm">
                <Save size={13} />{savingPlay ? "Saving…" : "Save"}
              </button>
            </div>
          </div>

          {/* A2: Canvas + Vertical Tool Panel side by side */}
          <div className="flex gap-2 items-start">

            {/* A2: Vertical tool panel (left of canvas) */}
            <div data-testid="tool-panel-vertical"
              className="flex-shrink-0 w-14 card py-3 px-1.5 flex flex-col gap-1 items-center">

              {/* Basic tools */}
              {TOOL_ITEMS.map(({ id, icon, label }) => (
                <button key={id} onClick={() => setTool(id)}
                  title={label}
                  className={clsx(
                    "w-full flex flex-col items-center gap-0.5 py-2 px-1 rounded-lg text-[9px] font-semibold transition-colors",
                    tool === id ? "bg-primary-600 text-white" : "text-slate-500 hover:bg-slate-100"
                  )}>
                  {icon}
                  {label}
                </button>
              ))}

              <div className="w-full border-t border-slate-100 my-1" />

              {/* Arrow styles */}
              {Object.entries(ARROW_STYLES).map(([key, s]) => (
                <button key={key} onClick={() => { setTool("arrow"); setArrowStyle(key as keyof typeof ARROW_STYLES); }}
                  title={s.label}
                  className={clsx(
                    "w-full flex flex-col items-center gap-0.5 py-2 px-1 rounded-lg text-[9px] font-semibold transition-colors",
                    tool === "arrow" && arrowStyle === key ? "bg-primary-600 text-white" : "text-slate-500 hover:bg-slate-100"
                  )}>
                  <Arrow size={13} style={{ color: tool === "arrow" && arrowStyle === key ? "white" : s.color }} />
                  {s.label}
                </button>
              ))}

              <div className="w-full border-t border-slate-100 my-1" />

              {/* Add Frame shortcut */}
              <button onClick={() => addFrame(false)}
                title="Add Frame"
                className="w-full flex flex-col items-center gap-0.5 py-2 px-1 rounded-lg text-[9px] font-semibold text-slate-500 hover:bg-slate-100 transition-colors">
                <Plus size={13} />
                Frame
              </button>
            </div>

            {/* Court canvas */}
            <div className="flex-1 card p-0 overflow-hidden">
              <CourtCanvas
                frame={{ players: currentFrame.players, arrows: currentFrame.arrows, freeform_paths: currentFrame.freeform_paths }}
                onUpdate={updateCurrentFrame}
                tool={tool}
                arrowStyle={arrowStyle}
                svgRef={svgRef}
                animating={animating}
              />
            </div>
          </div>

          {/* A3: Frame grid with mini courts + notes per frame */}
          <div className="card py-3 px-4">
            <div className="flex items-center gap-2 mb-3">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Frames</p>
              <button onClick={() => addFrame(false)} className="btn-ghost btn-sm text-xs" title="Duplicate frame">
                <Plus size={12} /> Duplicate
              </button>
              <button onClick={() => addFrame(true)} className="btn-ghost btn-sm text-xs" title="Add empty frame">
                <Plus size={12} /> Empty
              </button>
            </div>

            {/* A3: 2-column grid of frames, each with mini court + notes */}
            <div className="grid grid-cols-2 gap-3">
              {frames.map((f, i) => (
                <div key={i}
                  className={clsx(
                    "rounded-xl border-2 overflow-hidden cursor-pointer transition-colors",
                    i === currentFrameIdx ? "border-primary-500" : "border-slate-200 hover:border-slate-300"
                  )}
                  onClick={() => setCurrentFrameIdx(i)}>
                  {/* Frame header */}
                  <div className={clsx(
                    "flex items-center justify-between px-2 py-1",
                    i === currentFrameIdx ? "bg-primary-50" : "bg-slate-50"
                  )}>
                    <span className={clsx("text-[10px] font-bold", i === currentFrameIdx ? "text-primary-700" : "text-slate-500")}>
                      Frame {i + 1}
                    </span>
                    {frames.length > 1 && (
                      <button onClick={(e) => { e.stopPropagation(); deleteFrame(i); }}
                        className="h-4 w-4 rounded-full bg-red-100 text-red-500 text-[9px] flex items-center justify-center hover:bg-red-200 transition-colors">
                        ×
                      </button>
                    )}
                  </div>
                  {/* A3: Mini court visualization */}
                  <div className="px-1 pt-1">
                    <MiniCourt frame={f} />
                  </div>
                  {/* A3: Notes per frame */}
                  <div className="p-2" onClick={e => e.stopPropagation()}>
                    <p className="text-[9px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Play Notes</p>
                    <textarea
                      aria-label={`Frame ${i + 1} notes`}
                      className="w-full text-xs text-slate-600 bg-transparent border border-slate-200 rounded px-2 py-1 resize-none focus:outline-none focus:border-primary-400 placeholder:text-slate-300"
                      rows={2}
                      placeholder={`Notes for frame ${i + 1}…`}
                      value={f.notes}
                      onChange={(e) => setFrames(prev => prev.map((fr, fi) => fi === i ? { ...fr, notes: e.target.value } : fr))}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

export default function PlayBuilderPage() {
  return (
    <React.Suspense fallback={null}>
      <PlayBuilderContent />
    </React.Suspense>
  );
}
