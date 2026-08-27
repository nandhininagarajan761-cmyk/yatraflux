"use client";

import { useState, useCallback, useId } from "react";

interface ImpactedTrain {
  train_number: string;
  train_name: string;
  shared_station_code: string;
  conflict_type: "same_track_section" | "platform_conflict" | "crossing_precedence";
  estimated_secondary_delay_min: number;
  estimated_impact_time: string;
}

interface WhatIfResponse {
  origin_train_number: string;
  injected_delay_min: number;
  delay_station_code: string;
  total_network_delay_min: number;
  impacted_trains: ImpactedTrain[];
  cascade_depth: number;
  narrative: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

const CONFLICT_BADGES: Record<string, { label: string; style: string }> = {
  platform_conflict: {
    label: "Platform Conflict",
    style: "bg-rose-500/15 text-rose-300 ring-1 ring-rose-400/40",
  },
  same_track_section: {
    label: "Same Track Section",
    style: "bg-amber-500/15 text-amber-300 ring-1 ring-amber-400/40",
  },
  crossing_precedence: {
    label: "Crossing Precedence",
    style: "bg-purple-500/15 text-purple-300 ring-1 ring-purple-400/40",
  },
};

function formatClock(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-IN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return iso;
  }
}

export default function WhatIfSimulator() {
  const [trainNumber, setTrainNumber] = useState("12951");
  const [stationCode, setStationCode] = useState("BRC");
  const [injectedDelay, setInjectedDelay] = useState(30);
  const [horizonMin, setHorizonMin] = useState(120);

  const [result, setResult] = useState<WhatIfResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const formId = useId();

  const runSimulation = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/simulate/what-if`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          train_number: trainNumber.trim(),
          delay_station_code: stationCode.trim().toUpperCase(),
          injected_delay_min: injectedDelay,
          propagation_horizon_min: horizonMin,
        }),
      });

      if (!res.ok) {
        throw new Error(`Simulation failed (Status ${res.status})`);
      }

      const data: WhatIfResponse = await res.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run delay simulation.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [trainNumber, stationCode, injectedDelay, horizonMin]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void runSimulation();
  };

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6">
      {/* Simulation Form */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-xl shadow-xl sm:p-8">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-500/20 ring-1 ring-purple-400/30">
            <span className="text-xl">⚡</span>
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight text-slate-100 sm:text-2xl">
              What-If Network Delay Simulator
            </h2>
            <p className="text-xs text-slate-400">
              Graph-based cascade simulator modeling secondary track & platform bottlenecks.
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <div>
            <label htmlFor={`${formId}-train`} className="block text-xs font-medium text-slate-400">
              Origin Train No.
            </label>
            <input
              id={`${formId}-train`}
              value={trainNumber}
              onChange={(e) => setTrainNumber(e.target.value)}
              placeholder="e.g. 12951"
              className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-800/80 px-4 py-2.5 text-sm text-slate-100 outline-none focus:border-purple-400 focus:ring-1 focus:ring-purple-400"
            />
          </div>

          <div>
            <label htmlFor={`${formId}-station`} className="block text-xs font-medium text-slate-400">
              Injected Delay Station
            </label>
            <input
              id={`${formId}-station`}
              value={stationCode}
              onChange={(e) => setStationCode(e.target.value.toUpperCase())}
              placeholder="e.g. BRC"
              className="mt-1.5 w-full rounded-xl border border-slate-700 bg-slate-800/80 px-4 py-2.5 text-sm text-slate-100 uppercase tracking-wider outline-none focus:border-purple-400 focus:ring-1 focus:ring-purple-400"
            />
          </div>

          <div>
            <label htmlFor={`${formId}-delay`} className="block text-xs font-medium text-slate-400">
              Injected Delay: <span className="font-mono text-purple-300">{injectedDelay} min</span>
            </label>
            <input
              id={`${formId}-delay`}
              type="range"
              min={5}
              max={120}
              step={5}
              value={injectedDelay}
              onChange={(e) => setInjectedDelay(Number(e.target.value))}
              className="mt-3 h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-purple-400"
            />
          </div>

          <div>
            <label htmlFor={`${formId}-horizon`} className="block text-xs font-medium text-slate-400">
              Horizon Window: <span className="font-mono text-purple-300">{horizonMin} min</span>
            </label>
            <input
              id={`${formId}-horizon`}
              type="range"
              min={30}
              max={360}
              step={30}
              value={horizonMin}
              onChange={(e) => setHorizonMin(Number(e.target.value))}
              className="mt-3 h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-purple-400"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="col-span-1 mt-2 flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 px-6 py-3.5 text-sm font-semibold text-white shadow-lg shadow-purple-900/30 transition hover:from-purple-500 hover:to-indigo-500 disabled:opacity-50 sm:col-span-2"
          >
            {loading ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                Simulating Cascade Network Delay…
              </>
            ) : (
              "Run What-If Cascade Simulation"
            )}
          </button>
        </form>

        {error && (
          <p className="mt-4 rounded-xl bg-rose-500/10 px-4 py-3 text-xs text-rose-300 ring-1 ring-rose-500/30">
            {error}
          </p>
        )}
      </div>

      {/* Simulation Results */}
      {result && (
        <div className="space-y-6">
          {/* Summary KPIs */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-xl">
              <p className="text-[11px] uppercase tracking-wider text-slate-400">Injected Delay</p>
              <p className="mt-1 font-mono text-2xl font-bold text-amber-300">
                +{result.injected_delay_min} min
              </p>
              <p className="text-xs text-slate-500">Train #{result.origin_train_number} @ {result.delay_station_code}</p>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-xl">
              <p className="text-[11px] uppercase tracking-wider text-slate-400">Cumulative Network Delay</p>
              <p className="mt-1 font-mono text-2xl font-bold text-rose-400">
                +{result.total_network_delay_min} min
              </p>
              <p className="text-xs text-slate-500">Across {result.impacted_trains.length} downstream train(s)</p>
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-xl">
              <p className="text-[11px] uppercase tracking-wider text-slate-400">Cascade Hop Depth</p>
              <p className="mt-1 font-mono text-2xl font-bold text-purple-400">
                {result.cascade_depth} Hops
              </p>
              <p className="text-xs text-slate-500">Within {horizonMin} min horizon</p>
            </div>
          </div>

          {/* AI Dynamic Narrative Card */}
          <div className="rounded-2xl border border-purple-500/30 bg-purple-950/20 p-6 backdrop-blur-xl">
            <div className="flex items-start gap-3">
              <span className="text-2xl">🤖</span>
              <div>
                <h3 className="text-sm font-bold text-purple-200">Cascade Simulation Narrative</h3>
                <p className="mt-1 text-sm leading-relaxed text-slate-300">{result.narrative}</p>
              </div>
            </div>
          </div>

          {/* Secondary Impacted Trains */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-xl">
            <h3 className="mb-4 text-base font-semibold text-slate-100">
              Downstream Impacted Trains & Conflict Breakdown
            </h3>

            {result.impacted_trains.length === 0 ? (
              <p className="text-sm text-slate-400">No secondary trains affected within the horizon window.</p>
            ) : (
              <div className="space-y-3">
                {result.impacted_trains.map((train) => {
                  const badge = CONFLICT_BADGES[train.conflict_type] ?? CONFLICT_BADGES.same_track_section;
                  return (
                    <div
                      key={train.train_number}
                      className="flex flex-col items-start justify-between gap-3 rounded-xl border border-slate-800 bg-slate-800/40 p-4 sm:flex-row sm:items-center"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-bold text-slate-100">{train.train_name}</h4>
                          <span className="font-mono text-xs text-sky-400">#{train.train_number}</span>
                          <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold ${badge.style}`}>
                            {badge.label}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-slate-400">
                          Shared station: <span className="font-mono text-slate-200">{train.shared_station_code}</span> | Impact time: {formatClock(train.estimated_impact_time)}
                        </p>
                      </div>

                      <div className="rounded-lg bg-rose-500/10 px-3 py-1.5 text-right ring-1 ring-rose-500/30">
                        <p className="text-[10px] uppercase text-rose-300">Secondary Delay</p>
                        <p className="font-mono text-sm font-bold text-rose-400">
                          +{train.estimated_secondary_delay_min} min
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
