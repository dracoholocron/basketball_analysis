"use client";

import React, { createContext, useContext, useState, useEffect } from "react";

interface CoachModeContextValue {
  coachMode: boolean;
  setCoachMode: (v: boolean) => void;
}

const CoachModeContext = createContext<CoachModeContextValue>({
  coachMode: false,
  setCoachMode: () => {},
});

export function CoachModeProvider({ children }: { children: React.ReactNode }) {
  const [coachMode, setCoachModeState] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("coach_mode_v1");
    if (stored === "true") setCoachModeState(true);
  }, []);

  function setCoachMode(v: boolean) {
    setCoachModeState(v);
    localStorage.setItem("coach_mode_v1", String(v));
  }

  return (
    <CoachModeContext.Provider value={{ coachMode, setCoachMode }}>
      {children}
    </CoachModeContext.Provider>
  );
}

export function useCoachMode() {
  return useContext(CoachModeContext);
}
