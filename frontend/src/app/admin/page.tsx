"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Cookies from "js-cookie";
import AppShell from "@/components/layout/AppShell";
import { Building2, Trophy, Users, UserCircle2, ChevronRight } from "lucide-react";

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
];

export default function AdminPage() {
  const router = useRouter();
  useEffect(() => {
    if (!Cookies.get("access_token")) {
      router.replace("/login");
    }
  }, [router]);

  return (
    <AppShell title="Settings & Admin" subtitle="Manage your organization data">
      <div className="max-w-4xl mx-auto">
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
      </div>
    </AppShell>
  );
}
