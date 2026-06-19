"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Cookies from "js-cookie";
import AppShell from "@/components/layout/AppShell";
import { Building2, Trophy, Users, UserCircle2, ChevronRight, Dumbbell, Loader2, CheckCircle2, AlertCircle, Boxes } from "lucide-react";
import { triggerBallFinetune } from "@/lib/api";

const ADMIN_SECTIONS = [
  {
    href: "/admin/organizations",
    icon: <Building2 size={28} className="text-primary-600" />,
    title: "Organizations",
    description: "Manage organizations and their settings",
    color: "from-blue-50 to-indigo-50 border-blue-200",
  },
  {
    href: "/admin/seasons",
    icon: <Trophy size={28} className="text-amber-600" />,
    title: "Seasons",
    description: "Create and manage competitive seasons",
    color: "from-amber-50 to-yellow-50 border-amber-200",
  },
  {
    href: "/admin/teams",
    icon: <Users size={28} className="text-green-600" />,
    title: "Teams",
    description: "Add teams and configure roster details",
    color: "from-green-50 to-emerald-50 border-green-200",
  },
  {
    href: "/admin/players",
    icon: <UserCircle2 size={28} className="text-violet-600" />,
    title: "Players",
    description: "Register players, assign jersey numbers and positions",
    color: "from-violet-50 to-purple-50 border-violet-200",
  },
  {
    href: "/admin/models",
    icon: <Boxes size={28} className="text-sky-600" />,
    title: "Models",
    description: "Choose the active version of each model (player, ball, court, pose)",
    color: "from-sky-50 to-cyan-50 border-sky-200",
  },
];

export default function AdminPage() {
  const router = useRouter();
  const [ftState, setFtState] = useState<"idle" | "loading" | "ok" | "error">("idle");
  const [ftMsg, setFtMsg] = useState<string>("");

  useEffect(() => {
    if (!Cookies.get("access_token")) {
      router.replace("/login");
    }
  }, [router]);

  async function handleFinetune() {
    if (ftState === "loading") return;
    setFtState("loading");
    setFtMsg("");
    try {
      const res = await triggerBallFinetune();
      setFtState("ok");
      setFtMsg(`Reentrenamiento encolado (task ${res.task_id.slice(0, 8)}…). Corre en segundo plano en la GPU.`);
    } catch (err: unknown) {
      setFtState("error");
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setFtMsg(detail ?? (err instanceof Error ? err.message : "Error al encolar"));
    }
  }

  return (
    <AppShell title="Settings & Admin" subtitle="Manage your organization data">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          {ADMIN_SECTIONS.map((section) => (
            <Link key={section.href} href={section.href}>
              <div className={`
                card bg-gradient-to-br ${section.color}
                flex items-center gap-4 p-5 cursor-pointer
                hover:shadow-md hover:-translate-y-0.5 transition-all duration-200
              `}>
                <div className="p-3 rounded-xl bg-white shadow-sm">{section.icon}</div>
                <div className="flex-1 min-w-0">
                  <p className="font-display font-bold text-slate-900 text-base">{section.title}</p>
                  <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{section.description}</p>
                </div>
                <ChevronRight size={18} className="text-slate-400 flex-shrink-0" />
              </div>
            </Link>
          ))}
        </div>

        {/* Modelos / ML */}
        <div className="card bg-gradient-to-br from-rose-50 to-orange-50 border-rose-200 p-5">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-xl bg-white shadow-sm">
              <Dumbbell size={28} className="text-rose-600" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-display font-bold text-slate-900 text-base">Reentrenar detector de balón</p>
              <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
                Usa las cajas auto-etiquetadas por SAM2 (de los videos con balón anotado) para
                fine-tune del modelo. Corre en segundo plano en la GPU.
              </p>
            </div>
            <button
              onClick={handleFinetune}
              disabled={ftState === "loading"}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                ftState === "loading"
                  ? "bg-slate-300 text-slate-500 cursor-not-allowed"
                  : "bg-rose-600 hover:bg-rose-700 text-white"
              }`}
            >
              {ftState === "loading" ? <Loader2 size={14} className="animate-spin" /> : <Dumbbell size={14} />}
              Reentrenar
            </button>
          </div>
          {ftMsg && (
            <div className={`mt-3 flex items-center gap-2 text-xs ${ftState === "error" ? "text-red-600" : "text-green-700"}`}>
              {ftState === "error" ? <AlertCircle size={14} /> : <CheckCircle2 size={14} />}
              {ftMsg}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
