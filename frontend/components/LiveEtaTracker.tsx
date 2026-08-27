"use client";

import { useState, useCallback, useId } from "react";

interface DelayFactor {
  feature: string;
  impact_min: number;
  value: string;
  direction: "increases_delay" | "reduces_delay";
}

interface StationETA {
  station_code: string;
  station_name: string;
  sequence: number;
  scheduled_arrival: string;
  predicted_arrival: string;
  predicted_delay_min: number;
  confidence_low_min: number;
  confidence_high_min: number;
  recovery_min: number;
  top_factors: DelayFactor[];
}

interface TrainETAResponse {
  train_number: string;
  train_name: string;
  current_delay_min: number;
  last_known_station: string;
  generated_at: string;
  stations: StationETA[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

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

export default function LiveEtaTracker() {
  const [trainNumber, setTrainNumber] = useState("12951");
  const [data, setData] = useState<TrainETAResponse | null>(null);
  const [selectedStation, setSelectedStation] = useState<StationETA | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const formId = useId();

  const fetchEta = useCallback(async (num: string) => {
    if (!num.trim()) return;
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/trains/${num.trim()}/eta`);
      if (!res.ok) {
        throw new Error(`Train ${num} not found or server error.`);
      }
      const resData: TrainETAResponse = await res.json();
      setData(resData);
      if (resData.stations.length > 0) {
        setSelectedStation(resData.stations[1] ?? resData.stations[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load train ETA");
      setData(null);
      setSelectedStation(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    void fetchEta(trainNumber);
  };

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6">
      {/* Search Header */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-xl shadow-xl sm:p-8">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold tracking-tight text-slate-100 sm:text-2xl">
              Live Train ETA & SHAP Intelligence
            </h2>
            <p className="text-xs text-slate-400">
              Predictive route ETAs with LightGBM quantile confidence intervals and SHAP explainability.
            </p>
          </div>
          <span className="hidden rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-400 ring-1 ring-emerald-500/30 sm:block">
            Live Stream
          </span>
        </div>

        <form onSubmit={handleSearch} className="flex gap-3">
          <div className="relative flex-1">
            <input
              id={`${formId}-train`}
              type="text"
              value={trainNumber}
              onChange={(e) => setTrainNumber(e.target.value)}
              placeholder="Enter Train Number (e.g. 12951)"
              className="w-full rounded-xl border border-slate-700 bg-slate-800/80 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500 outline-none transition focus:border-sky-400 focus:ring-1 focus:ring-sky-400"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-sky-500 to-blue-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-sky-900/30 transition hover:from-sky-400 hover:to-blue-500 disabled:opacity-50"
          >
            {loading ? (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            ) : (
              "Track ETA"
            )}
          </button>
        </form>

        {error && (
          <p className="mt-4 rounded-xl bg-rose-500/10 px-4 py-3 text-xs text-rose-300 ring-1 ring-rose-500/30">
            {error}
          </p>
        )}
      </div>

      {data && (
        <div className="space-y-6">
          {/* Train Status Overview Banner */}
          <div className="grid grid-cols-1 gap-4 rounded-2xl border border-slate-800 bg-slate-900/50 p-6 backdrop-blur-xl sm:grid-cols-3">
            <div className="rounded-xl border border-slate-800 bg-slate-800/40 p-4">
              <p className="text-[11px] uppercase tracking-wider text-slate-400">Train Info</p>
              <h3 className="mt-1 text-lg font-bold text-slate-100">{data.train_name}</h3>
              <p className="font-mono text-xs text-sky-400">#{data.train_number}</p>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-800/40 p-4">
              <p className="text-[11px] uppercase tracking-wider text-slate-400">Current Delay</p>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="font-mono text-2xl font-bold text-rose-400">
                  +{data.current_delay_min.toFixed(0)}
                </span>
                <span className="text-xs text-slate-400">min</span>
              </div>
              <p className="text-[11px] text-slate-500">Last reported at {data.last_known_station}</p>
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-800/40 p-4">
              <p className="text-[11px] uppercase tracking-wider text-slate-400">Prediction Engine</p>
              <div className="mt-1 flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-sm font-semibold text-slate-200">LightGBM + SHAP</span>
              </div>
              <p className="text-[11px] text-slate-400">Quantile P10 – P90 Active</p>
            </div>
          </div>

          {/* Route Timeline & Confidence Intervals */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-xl">
            <h3 className="mb-4 text-base font-semibold text-slate-100">
              Station Route & Confidence Intervals (P10 – P90)
            </h3>

            <div className="space-y-4">
              {data.stations.map((s) => {
                const isSelected = selectedStation?.station_code === s.station_code;
                return (
                  <div
                    key={s.station_code}
                    onClick={() => setSelectedStation(s)}
                    className={`cursor-pointer rounded-xl border p-4 transition-all ${
                      isSelected
                        ? "border-sky-500/60 bg-sky-950/30 ring-1 ring-sky-500/40 shadow-lg"
                        : "border-slate-800 bg-slate-800/30 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      {/* Station Info */}
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-700/60 font-mono text-xs font-bold text-sky-300">
                          {s.sequence}
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="text-sm font-bold text-slate-100">{s.station_name}</h4>
                            <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                              {s.station_code}
                            </span>
                          </div>
                          <p className="text-xs text-slate-400">
                            Sched: {formatClock(s.scheduled_arrival)} | Pred:{" "}
                            <span className="font-semibold text-sky-300">
                              {formatClock(s.predicted_arrival)}
                            </span>
                          </p>
                        </div>
                      </div>

                      {/* Confidence Interval Visualizer */}
                      <div className="w-full sm:w-72">
                        <div className="flex justify-between text-[11px] font-mono text-slate-400">
                          <span>P10: +{s.confidence_low_min}m</span>
                          <span className="font-bold text-rose-300">
                            +{s.predicted_delay_min}m delay
                          </span>
                          <span>P90: +{s.confidence_high_min}m</span>
                        </div>
                        {/* Range Bar */}
                        <div className="relative mt-1.5 h-2.5 w-full rounded-full bg-slate-800 overflow-hidden">
                          <div
                            className="absolute h-full rounded-full bg-gradient-to-r from-emerald-500 via-amber-400 to-rose-500 opacity-80"
                            style={{
                              left: `${Math.max(0, Math.min(100, s.confidence_low_min * 3))}%`,
                              width: `${Math.max(
                                10,
                                Math.min(100, (s.confidence_high_min - s.confidence_low_min) * 3)
                              )}%`,
                            }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* SHAP Feature Explanation Panel */}
          {selectedStation && (
            <div className="rounded-2xl border border-sky-500/30 bg-slate-900/80 p-6 backdrop-blur-xl shadow-2xl">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-lg">🧠</span>
                    <h3 className="text-base font-bold text-slate-100">
                      SHAP Delay Intelligence — {selectedStation.station_name} ({selectedStation.station_code})
                    </h3>
                  </div>
                  <p className="text-xs text-slate-400">
                    Model attribution breakdown showing why the predicted delay is +
                    {selectedStation.predicted_delay_min} minutes.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {selectedStation.top_factors.map((factor, idx) => {
                  const isInc = factor.direction === "increases_delay";
                  return (
                    <div
                      key={idx}
                      className={`flex items-center justify-between rounded-xl border p-3.5 ${
                        isInc
                          ? "border-rose-500/20 bg-rose-950/20 text-rose-200"
                          : "border-emerald-500/20 bg-emerald-950/20 text-emerald-200"
                      }`}
                    >
                      <div>
                        <p className="text-xs font-semibold">{factor.feature}</p>
                        <p className="text-[11px] opacity-75">Recorded value: {factor.value}</p>
                      </div>
                      <span
                        className={`rounded-lg px-2.5 py-1 font-mono text-xs font-bold ${
                          isInc
                            ? "bg-rose-500/20 text-rose-300 ring-1 ring-rose-500/40"
                            : "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/40"
                        }`}
                      >
                        {isInc ? `+${factor.impact_min} min` : `${factor.impact_min} min`}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
