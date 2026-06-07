"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import { listTrainingSessions, createTrainingSession, uploadTrainingVideo } from "@/lib/api";
import { Dumbbell, Plus, Loader2, Upload, ChevronRight, CheckCircle2, AlertCircle, Clock } from "lucide-react";
import { clsx } from "clsx";

interface TrainingSession {
  id: string;
  sport_drill: string | null;
  status: string;
  video_s3_key: string | null;
  created_at: string;
}

const STATUS_CONFIG: Record<string, { color: string; icon: React.ReactNode }> = {
  pending:   { color: "text-slate-400",  icon: <Clock size={14} /> },
  uploaded:  { color: "text-blue-500",   icon: <Upload size={14} /> },
  analyzing: { color: "text-amber-500",  icon: <Loader2 size={14} className="animate-spin" /> },
  done:      { color: "text-green-600",  icon: <CheckCircle2 size={14} /> },
  failed:    { color: "text-red-500",    icon: <AlertCircle size={14} /> },
};

export default function TrainingPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<TrainingSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [drillName, setDrillName] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [uploadingFor, setUploadingFor] = useState<string | null>(null);

  useEffect(() => {
    listTrainingSessions()
      .then(data => setSessions(Array.isArray(data) ? data : data.items ?? data))
      .catch(() => router.replace("/login"))
      .finally(() => setLoading(false));
  }, [router]);

  async function handleCreate() {
    setCreating(true);
    try {
      const session = await createTrainingSession({ sport_drill: drillName || "Free Shooting" });
      setSessions(prev => [session, ...prev]);
      setShowCreate(false);
      setDrillName("");
    } catch (err) { console.error("Create session failed:", err); }
    finally { setCreating(false); }
  }

  async function handleUpload(sessionId: string, file: File) {
    setUploadingFor(sessionId);
    try {
      await uploadTrainingVideo(sessionId, file);
      const updated = await listTrainingSessions();
      setSessions(Array.isArray(updated) ? updated : updated.items ?? updated);
    } catch (err) { console.error("Upload failed:", err); }
    finally { setUploadingFor(null); }
  }

  return (
    <AppShell title="Training" subtitle="Pose estimation & shooting form analysis">
      <div className="max-w-3xl mx-auto space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Dumbbell size={20} className="text-primary-600" />
            <h2 className="text-lg font-bold text-slate-800">Training Sessions</h2>
          </div>
          <button onClick={() => setShowCreate(v => !v)} className="btn-primary btn-sm">
            <Plus size={14} /> New Session
          </button>
        </div>

        {/* Create form */}
        {showCreate && (
          <div className="card space-y-3">
            <p className="text-sm font-semibold text-slate-700">New Training Session</p>
            <input
              className="input w-full"
              placeholder="Drill name (e.g. Free Shooting, Layups...)"
              value={drillName}
              onChange={e => setDrillName(e.target.value)}
            />
            <div className="flex gap-2">
              <button onClick={handleCreate} disabled={creating} className="btn-primary btn-sm">
                {creating ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
                Create
              </button>
              <button onClick={() => setShowCreate(false)} className="btn-ghost btn-sm">Cancel</button>
            </div>
          </div>
        )}

        {/* Sessions list */}
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={24} className="animate-spin text-slate-400" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="card text-center py-12">
            <Dumbbell size={32} className="text-slate-200 mx-auto mb-3" />
            <p className="text-slate-400 text-sm">No training sessions yet.</p>
            <p className="text-slate-400 text-xs mt-1">Create one and upload a video clip to analyze shooting form.</p>
          </div>
        ) : (
          <div className="card p-0 divide-y divide-slate-50">
            {sessions.map((s) => {
              const statusCfg = STATUS_CONFIG[s.status] ?? STATUS_CONFIG.pending;
              return (
                <div key={s.id} className="flex items-center gap-4 px-4 py-3">
                  <div className={clsx("flex items-center gap-1.5", statusCfg.color)}>
                    {statusCfg.icon}
                    <span className="text-xs font-semibold capitalize">{s.status}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">
                      {s.sport_drill ?? "Training Session"}
                    </p>
                    <p className="text-[10px] text-slate-400">
                      {new Date(s.created_at).toLocaleDateString()}
                    </p>
                  </div>

                  {/* Upload video button */}
                  {!s.video_s3_key && (
                    <label className={clsx("btn-secondary btn-sm cursor-pointer", uploadingFor === s.id && "opacity-50")}>
                      {uploadingFor === s.id ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
                      Upload Video
                      <input type="file" accept="video/*" className="sr-only"
                        disabled={uploadingFor === s.id}
                        onChange={e => { const f = e.target.files?.[0]; if (f) handleUpload(s.id, f); e.target.value = ""; }} />
                    </label>
                  )}

                  {/* View details */}
                  <Link href={`/training/${s.id}`} className="text-primary-600 hover:text-primary-700">
                    <ChevronRight size={18} />
                  </Link>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </AppShell>
  );
}
