"use client";

import Sidebar from "./Sidebar";
import { CoachModeToggle } from "@/components/CoachModeToggle";

interface AppShellProps {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

export default function AppShell({ children, title, subtitle, actions }: AppShellProps) {
  return (
    <div className="flex min-h-screen bg-surface">
      <Sidebar />
      <div className="flex flex-1 flex-col pl-64">
        <header className="sticky top-0 z-40 flex h-16 items-center justify-between border-b border-surface-border bg-white/95 px-6 backdrop-blur-sm">
          <div>
            {title && <h1 className="page-title text-xl">{title}</h1>}
            {subtitle && <p className="page-subtitle">{subtitle}</p>}
          </div>
          <div className="flex items-center gap-3">
            <CoachModeToggle />
            {actions && <>{actions}</>}
          </div>
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
