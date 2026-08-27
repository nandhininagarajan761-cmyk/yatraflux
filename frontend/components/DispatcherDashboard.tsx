"use client";

import { useState, useEffect, useCallback } from "react";

interface StationCongestionInfo {
  station_code: string;
  station_name: string;
  avg_delay_min: number;
  platform_congestion: number;
  active_trains_count: number;
}

interface ActiveTrainStatus {
  train_number: string;
  train_name: string;
  current_delay_min: number;
  last_station_code: string;
}

interface NetworkStatusResponse {
  active_trains_count: number;
  network_avg_delay_min: number;
  high_risk_junctions_count: number;
  congested_stations: StationCongestionInfo[];
  recent_trains: ActiveTrainStatus[];
  prediction_mode: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export default function DispatcherDashboard() {
  const [data, setData] = useState<NetworkStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/network/status`);
      if (!res.ok) {
        throw new Error("Failed to fetch network status.");
      }
      const resData: NetworkStatusResponse = await res.json();
      setData(resData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error loading dashboard");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      {/* Header */}
      <div className="flex flex-col items-start justify-between gap-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-xl shadow-xl sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold tracking-tight text-slate-100 sm:text-2xl">
              Network Dispatcher Dashboard
            </h2>
            <span className="rounded-full bg-sky-500/10 px-2.5 py-0.5 text-xs font-semibold text-sky-400 ring-1 ring-sky-500/30">
              Operator View
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Real-time railway network health, platform congestion monitoring, and active delay risks.
          </p>
        </div>

        <button
          onClick={() => void fetchStatus()}
          disabled={loading}
          className="flex items-center gap-2 rounded-xl bg-slate-800 px-4 py-2.5 text-xs font-medium text-slate-200 transition hover:bg-slate-700"
        >
          <span className={loading ? "animate-spin" : ""}>🔄</span>
          <span>Refresh Feed</span>
        </button>
      </div>

      {error && (
        <p className="rounded-xl bg-rose-500/10 px-4 py-3 text-xs text-rose-300 ring-1 ring-rose-500/30">
          {error}
        </p>
      )}

      {data && (
        <div className="space-y-6">
          {/* System KPIs */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-xl">
              <p className="text-[11px] uppercase tracking-wider text-slate-400">Active Trains Managed</p>
              <p className="mt-1 font-mono text-3xl font-bold text-sky-400">{data.active_trains_count}</p>
              <p className="text-xs text-slate-500">Live operational fleet</p>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-xl">
              <p className="text-[11px] uppercase tracking-wider text-slate-400">Avg Network Delay</p>
              <p className="mt-1 font-mono text-3xl font-bold text-amber-300">
                +{data.network_avg_delay_min} min
              </p>
              <p className="text-xs text-slate-500">System-wide section average</p>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-xl">
              <p className="text-[11px] uppercase tracking-wider text-slate-400">Congested Junctions</p>
              <p className="mt-1 font-mono text-3xl font-bold text-rose-400">
                {data.high_risk_junctions_count}
              </p>
              <p className="text-xs text-slate-500">Platform load &gt; 35%</p>
            </div>
          </div>

          {/* Junction Congestion Table */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-xl">
            <h3 className="mb-4 text-base font-semibold text-slate-100">
              Junction & Platform Congestion Heatmap
            </h3>
            <div className="space-y-3">
              {data.congested_stations.map((st) => {
                const congPct = Math.round(st.platform_congestion * 100);
                return (
                  <div
                    key={st.station_code}
                    className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-800/30 p-4 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-700/60 font-mono text-xs font-bold text-slate-200">
                        {st.station_code}
                      </div>
                      <div>
                        <h4 className="text-sm font-bold text-slate-100">{st.station_name}</h4>
                        <p className="text-xs text-slate-400">
                          Active Trains: {st.active_trains_count} | Section Avg Delay: +{st.avg_delay_min}m
                        </p>
                      </div>
                    </div>

                    <div className="w-full sm:w-60">
                      <div className="flex justify-between text-xs font-mono text-slate-400">
                        <span>Platform Load</span>
                        <span className={congPct > 40 ? "text-rose-400 font-bold" : "text-emerald-400"}>
                          {congPct}%
                        </span>
                      </div>
                      <div className="mt-1.5 h-2.5 w-full rounded-full bg-slate-800 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            congPct > 40 ? "bg-rose-500" : "bg-emerald-500"
                          }`}
                          style={{ width: `${Math.min(100, congPct)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Live Fleet Status */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-xl">
            <h3 className="mb-4 text-base font-semibold text-slate-100">
              Active Fleet Real-Time Status Feed
            </h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {data.recent_trains.map((train) => (
                <div
                  key={train.train_number}
                  className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-800/40 p-4"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <h4 className="text-sm font-bold text-slate-100">{train.train_name}</h4>
                      <span className="font-mono text-xs text-sky-400">#{train.train_number}</span>
                    </div>
                    <p className="text-xs text-slate-400">
                      Last station: <span className="font-mono text-slate-200">{train.last_station_code}</span>
                    </p>
                  </div>
                  <span
                    className={`rounded-lg px-2.5 py-1 font-mono text-xs font-bold ${
                      train.current_delay_min > 15
                        ? "bg-rose-500/20 text-rose-300 ring-1 ring-rose-500/40"
                        : "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40"
                    }`}
                  >
                    +{train.current_delay_min} min
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
