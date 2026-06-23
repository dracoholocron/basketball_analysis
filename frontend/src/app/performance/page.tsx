"use client";

import { useEffect, useState } from "react";
import AppShell from "@/components/layout/AppShell";
import { getPerformanceSummary, type PerformanceSummary } from "@/lib/api";
import { clsx } from "clsx";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { Loader2, Activity } from "lucide-react";

type Period = "daily" | "monthly" | "yearly";

export default function PerformancePage() {
  const [period, setPeriod] = useState<Period>("daily");
  const [data, setData] = useState<PerformanceSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getPerformanceSummary(period)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [period]);

  const series = (data?.series ?? []).map(p => ({
    period: p.period,
    coverage: p.avg_coverage_pct ?? 0,
    rawRate: p.avg_raw_detection_rate != null ? Math.round(p.avg_raw_detection_rate * 100) : 0,
    minutes: p.avg_total_seconds != null ? Math.round(p.avg_total_seconds / 60) : 0,
    fps: p.avg_fps_processed ?? 0,
    runs: p.runs,
  }));

  return (
    <AppShell title="Rendimiento" subtitle="Calidad de detección, tiempo y eficiencia de los modelos">
      <div className="space-y-5">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-slate-400 flex items-center gap-2">
            <Activity size={16} /> {data?.total_runs ?? 0} análisis registrados ·
            <span className="text-slate-500">métricas proxy de calidad de detección (sin ground-truth)</span>
          </p>
          <div className="flex items-center gap-1 bg-slate-800 rounded-lg p-1">
            {(["daily", "monthly", "yearly"] as Period[]).map(p => (
              <button key={p} onClick={() => setPeriod(p)}
                className={clsx("px-3 py-1.5 text-xs rounded-md transition-colors",
                  period === p ? "bg-blue-600 text-white" : "text-slate-400 hover:text-white")}>
                {p === "daily" ? "Diario" : p === "monthly" ? "Mensual" : "Anual"}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-slate-400 py-10 justify-center">
            <Loader2 className="animate-spin" size={18} /> Cargando…
          </div>
        ) : series.length === 0 ? (
          <div className="text-slate-500 text-sm py-10 text-center">
            Sin datos todavía. Las estadísticas aparecen a medida que se completan análisis.
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
                <p className="text-sm font-semibold text-white mb-3">Calidad de detección de balón (%)</p>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={series}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="period" stroke="#94a3b8" fontSize={11} />
                    <YAxis stroke="#94a3b8" fontSize={11} domain={[0, 100]} />
                    <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }} />
                    <Legend />
                    <Line type="monotone" dataKey="coverage" name="Cobertura %" stroke="#3b82f6" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="rawRate" name="Detección directa %" stroke="#10b981" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
                <p className="text-sm font-semibold text-white mb-3">Tiempo medio de análisis (min) y FPS</p>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={series}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="period" stroke="#94a3b8" fontSize={11} />
                    <YAxis stroke="#94a3b8" fontSize={11} />
                    <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8 }} />
                    <Legend />
                    <Bar dataKey="minutes" name="Min/análisis" fill="#6366f1" />
                    <Bar dataKey="fps" name="FPS" fill="#f59e0b" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
              <p className="text-sm font-semibold text-white mb-3">Comparativa por detector de balón</p>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-400 text-xs border-b border-slate-700">
                    <th className="text-left py-2">Detector</th>
                    <th className="text-right py-2">Análisis</th>
                    <th className="text-right py-2">Cobertura media</th>
                    <th className="text-right py-2">Detección directa media</th>
                    <th className="text-right py-2">Tiempo medio</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.detectors ?? []).map(d => (
                    <tr key={d.detector} className="border-b border-slate-700/50">
                      <td className="py-2 text-white font-mono">{d.detector}</td>
                      <td className="py-2 text-right text-slate-300">{d.runs}</td>
                      <td className="py-2 text-right text-slate-300">{d.avg_coverage_pct != null ? `${d.avg_coverage_pct.toFixed(1)}%` : "—"}</td>
                      <td className="py-2 text-right text-slate-300">{d.avg_raw_detection_rate != null ? `${(d.avg_raw_detection_rate * 100).toFixed(1)}%` : "—"}</td>
                      <td className="py-2 text-right text-slate-300">{d.avg_total_seconds != null ? `${Math.round(d.avg_total_seconds / 60)} min` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
