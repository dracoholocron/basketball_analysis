"use client";

// Simple module-level store (no external deps needed)
let _selfScout = false;
const _listeners: Set<() => void> = new Set();

function getState() {
  return _selfScout;
}

function toggleState() {
  _selfScout = !_selfScout;
  _listeners.forEach((fn) => fn());
}

// React hook for self-scout state
import { useState, useEffect } from "react";

export function useSelfScout() {
  const [selfScout, setSelfScout] = useState(_selfScout);

  useEffect(() => {
    const listener = () => setSelfScout(_selfScout);
    _listeners.add(listener);
    return () => { _listeners.delete(listener); };
  }, []);

  return { selfScout, toggle: toggleState };
}
