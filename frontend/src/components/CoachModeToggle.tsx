"use client";

import { useCoachMode } from "@/contexts/CoachModeContext";
import { Megaphone } from "lucide-react";
import { clsx } from "clsx";

export function CoachModeToggle() {
  const { coachMode, setCoachMode } = useCoachMode();

  return (
    <button
      onClick={() => setCoachMode(!coachMode)}
      className={clsx(
        "inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full border transition-colors",
        coachMode
          ? "bg-amber-500 text-white border-amber-500 hover:bg-amber-600"
          : "bg-white text-slate-500 border-slate-200 hover:bg-slate-50"
      )}
      title={coachMode ? "Coach Mode ON — showing huddle-speak" : "Coach Mode OFF"}
    >
      <Megaphone size={12} />
      Coach Mode
    </button>
  );
}
