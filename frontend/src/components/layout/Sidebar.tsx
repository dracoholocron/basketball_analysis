"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { logout } from "@/lib/api";
import { clsx } from "clsx";
import {
  LayoutDashboard,
  Video,
  Search,
  CalendarDays,
  Activity,
  PenTool,
  Settings,
  Layers,
  LogOut,
  FlipHorizontal,
  ChevronRight,
  TableProperties,
  Building2,
  Trophy,
  Users,
  UserCircle2,
  Dumbbell,
  Swords,
} from "lucide-react";
import { useSelfScout } from "@/lib/selfScout";

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
  group: string;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Dashboard", icon: <LayoutDashboard size={18} />, group: "main" },
  { href: "/games", label: "Games & Video", icon: <Video size={18} />, group: "main" },
  { href: "/scouting", label: "Scouting", icon: <Search size={18} />, group: "analysis" },
  { href: "/game-day", label: "Game Day", icon: <CalendarDays size={18} />, group: "analysis" },
  { href: "/game-tracker", label: "Game Tracker", icon: <Activity size={18} />, group: "analysis" },
  { href: "/play-builder", label: "Play Builder", icon: <PenTool size={18} />, group: "tools" },
  { href: "/training", label: "Training", icon: <Dumbbell size={18} />, group: "tools" },
  { href: "/matchups", label: "Matchup Workspace", icon: <Swords size={18} />, group: "tools" },
  { href: "/admin/box-scores", label: "Box Scores", icon: <TableProperties size={18} />, group: "tools" },
  { href: "/jobs", label: "Analysis Jobs", icon: <Layers size={18} />, group: "tools" },
  { href: "/admin", label: "Settings", icon: <Settings size={18} />, group: "system" },
  { href: "/admin/organizations", label: "Organizations", icon: <Building2 size={18} />, group: "system" },
  { href: "/admin/seasons", label: "Seasons", icon: <Trophy size={18} />, group: "system" },
  { href: "/admin/teams", label: "Teams", icon: <Users size={18} />, group: "system" },
  { href: "/admin/players", label: "Players", icon: <UserCircle2 size={18} />, group: "system" },
];

export default function Sidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const { selfScout, toggle } = useSelfScout();

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    if (href === "/admin") return pathname === "/admin"; // exact match only for admin dashboard
    return pathname.startsWith(href);
  }

  const mainItems = NAV_ITEMS.filter((i) => i.group === "main");
  const analysisItems = NAV_ITEMS.filter((i) => i.group === "analysis");
  const toolsItems = NAV_ITEMS.filter((i) => i.group === "tools");
  const systemItems = NAV_ITEMS.filter((i) => i.group === "system");

  return (
    <aside className="fixed inset-y-0 left-0 z-50 flex w-64 flex-col bg-sidebar-bg border-r border-sidebar-border">
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 px-5 border-b border-sidebar-border">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600 text-white font-bold text-sm shadow-sm">
          IQ
        </div>
        <div>
          <p className="text-sm font-bold text-white leading-tight">Basketball IQ</p>
          <p className="text-[10px] text-slate-500 font-medium uppercase tracking-wider">AI Analytics</p>
        </div>
      </div>

      {/* Self-Scout Banner */}
      {selfScout && (
        <div className="mx-3 mt-3 rounded-lg bg-violet-600/20 border border-violet-500/30 px-3 py-2">
          <p className="text-[10px] font-semibold text-violet-400 uppercase tracking-wider">Self-Scout Mode</p>
          <p className="text-[10px] text-violet-300 mt-0.5">Viewing as opponent</p>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
        <NavGroup label="Overview" items={mainItems} isActive={isActive} />
        <NavGroup label="Analysis" items={analysisItems} isActive={isActive} />
        <NavGroup label="Tools" items={toolsItems} isActive={isActive} />
        <div className="space-y-0.5">
          {systemItems.map((item) => (
            <NavLink key={item.href} item={item} active={isActive(item.href)} />
          ))}
        </div>
      </nav>

      {/* Footer */}
      <div className="border-t border-sidebar-border px-3 py-4 space-y-1">
        {/* Self-Scout Toggle */}
        <button
          onClick={toggle}
          className={clsx(
            "flex items-center gap-3 rounded-lg px-3 py-2.5 w-full text-sm font-medium transition-all duration-150",
            selfScout
              ? "text-violet-400 hover:bg-violet-500/10"
              : "text-slate-500 hover:bg-sidebar-hover hover:text-slate-400"
          )}
        >
          <FlipHorizontal size={18} />
          <span>Self-Scout</span>
          <div className={clsx(
            "ml-auto h-5 w-9 rounded-full relative flex-shrink-0 transition-colors",
            selfScout ? "bg-violet-600" : "bg-slate-700"
          )}>
            <div className={clsx(
              "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform",
              selfScout ? "translate-x-4" : "translate-x-0.5"
            )} />
          </div>
        </button>

        {/* Sign out */}
        <button
          onClick={handleLogout}
          className="nav-item w-full text-left text-danger-500 hover:text-danger-400 hover:bg-danger-500/10"
        >
          <LogOut size={18} />
          <span>Sign Out</span>
        </button>
      </div>
    </aside>
  );
}

function NavGroup({ label, items, isActive }: { label: string; items: NavItem[]; isActive: (href: string) => boolean }) {
  return (
    <div>
      <p className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-widest text-slate-600">{label}</p>
      <div className="space-y-0.5">
        {items.map((item) => (
          <NavLink key={item.href} item={item} active={isActive(item.href)} />
        ))}
      </div>
    </div>
  );
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <Link href={item.href} className={clsx(active ? "nav-item-active" : "nav-item")}>
      {item.icon}
      <span>{item.label}</span>
      {active && <ChevronRight size={14} className="ml-auto opacity-60" />}
    </Link>
  );
}
