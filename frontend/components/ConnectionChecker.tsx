"use client";

/**
 * ConnectionChecker — YatraFlux AI command-center widget.
 *
 * Lets a passenger enter their current train, connecting train, and the
 * junction station, then calls POST /api/connections/risk and renders the
 * success probability, a risk badge, an explanation, and alternative trains.
 *
 * Types below mirror app/main.py's Pydantic schemas field-for-field so the
 * frontend/backend contract stays in lockstep.
 */

import { useState, useCallback, useId } from "react";

// ---------------------------------------------------------------------------
// Types — mirror ConnectionRiskRequest / ConnectionRiskResponse exactly
// ---------------------------------------------------------------------------

type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

interface ConnectionRiskRequest {
  primary_train_number: string;
  connecting_train_number: string;
  connection_station_code: string;
  buffer_min: number;
}

interface AlternativeTrain {
  train_number: string;
  train_name: string;
  departure_time: string; // ISO datetime
  success_probability: number;
}

interface ConnectionRiskResponse {
  primary_train_number: string;
  connecting_train_number: string;
  connection_station_code: string;
  primary_predicted_arrival: string; // ISO datetime
  connecting_scheduled_departure: string; // ISO datetime
  effective_buffer_min: number;
  required_buffer_min: number;
  success_probability: number;
  risk_level: RiskLevel;
  explanation: string;
  alternative_trains: AlternativeTrain[];
}

interface ApiErrorBody {
  detail?: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

// ---------------------------------------------------------------------------
// Risk styling — one source of truth for badge + gauge colors
// ---------------------------------------------------------------------------

const RISK_STYLES: Record<
  RiskLevel,
  { label: string; badge: string; ring: string; glow: string }
> = {
  LOW: {
    label: "Low risk",
    badge: "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-400/40",
    ring: "#34d399",
    glow: "shadow-[0_0_24px_-4px_rgba(52,211,153,0.55)]",
  },
  MEDIUM: {
    label: "Medium risk",
    badge: "bg-amber-500/15 text-amber-300 ring-1 ring-amber-400/40",
    ring: "#fbbf24",
    glow: "shadow-[0_0_24px_-4px_rgba(251,191,36,0.55)]",
  },
  HIGH: {
    label: "High risk",
    badge: "bg-rose-500/15 text-rose-300 ring-1 ring-rose-400/40",
    ring: "#fb7185",
    glow: "shadow-[0_0_24px_-4px_rgba(251,113,133,0.55)]",
  },
};

function formatClock(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

// ---------------------------------------------------------------------------
// Sub-component: circular probability gauge (the widget's signature element)
// ---------------------------------------------------------------------------

function ProbabilityGauge({
  probability,
  color,
}: {
  probability: number;
  color: string;
}) {
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - probability / 100);

  return (
    <div className="relative flex h-36 w-36 shrink-0 items-center justify-center">
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
        <circle
          cx="60"
          cy="60"
          r={radius}
          fill="none"
          stroke="rgba(148,163,184,0.15)"
          strokeWidth="10"
        />
        <circle
          cx="60"
          cy="60"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-[stroke-dashoffset] duration-700 ease-out"
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="font-mono text-3xl font-semibold tabular-nums text-slate-50">
          {probability.toFixed(0)}
          <span className="text-lg text-slate-400">%</span>
        </span>
        <span className="text-[10px] uppercase tracking-[0.2em] text-slate-500">
          success
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ConnectionChecker() {
  const [primaryTrain, setPrimaryTrain] = useState("");
  const [connectingTrain, setConnectingTrain] = useState("");
  const [stationCode, setStationCode] = useState("");
  const [bufferMin, setBufferMin] = useState(20);

  const [result, setResult] = useState<ConnectionRiskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const formId = useId();

  const isValid =
    /^\d+$/.test(primaryTrain.trim()) &&
    /^\d+$/.test(connectingTrain.trim()) &&
    stationCode.trim().length >= 2;

  const checkConnection = useCallback(async () => {
    if (!isValid) {
      setError("Enter valid train numbers and a station code to continue.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);

    const payload: ConnectionRiskRequest = {
      primary_train_number: primaryTrain.trim(),
      connecting_train_number: connectingTrain.trim(),
      connection_station_code: stationCode.trim().toUpperCase(),
      buffer_min: bufferMin,
    };

    try {
      const res = await fetch(`${API_BASE}/api/connections/risk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as ApiErrorBody;
        throw new Error(body.detail ?? `Request failed with status ${res.status}`);
      }

      const data: ConnectionRiskResponse = await res.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }, [primaryTrain, connectingTrain, stationCode, bufferMin, isValid]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void checkConnection();
  };

  const riskStyle = result ? RISK_STYLES[result.risk_level] : null;

  return (
    <div className="mx-auto w-full max-w-2xl rounded-2xl border border-slate-700/40 bg-slate-900/60 p-6 backdrop-blur-xl shadow-[0_8px_40px_-12px_rgba(15,23,42,0.9)] sm:p-8">
      {/* Header */}
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500/20 to-blue-600/20 ring-1 ring-sky-400/30">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.75}
            className="h-5 w-5 text-sky-300"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 21c4-4 7-7.582 7-11a7 7 0 10-14 0c0 3.418 3 7 7 11z" />
            <circle cx="12" cy="10" r="2.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-slate-50">
            Connection Risk Checker
          </h2>
          <p className="text-sm text-slate-400">
            Will your connecting train wait long enough?
          </p>
        </div>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Your train no." htmlFor={`${formId}-primary`}>
          <input
            id={`${formId}-primary`}
            inputMode="numeric"
            placeholder="e.g. 12951"
            value={primaryTrain}
            onChange={(e) => setPrimaryTrain(e.target.value)}
            className={inputClass}
          />
        </Field>

        <Field label="Connecting train no." htmlFor={`${formId}-connecting`}>
          <input
            id={`${formId}-connecting`}
            inputMode="numeric"
            placeholder="e.g. 12009"
            value={connectingTrain}
            onChange={(e) => setConnectingTrain(e.target.value)}
            className={inputClass}
          />
        </Field>

        <Field label="Junction station code" htmlFor={`${formId}-station`}>
          <input
            id={`${formId}-station`}
            placeholder="e.g. BRC"
            value={stationCode}
            onChange={(e) => setStationCode(e.target.value.toUpperCase())}
            className={`${inputClass} uppercase tracking-wider`}
            maxLength={8}
          />
        </Field>

        <Field label={`Minimum buffer: ${bufferMin} min`} htmlFor={`${formId}-buffer`}>
          <input
            id={`${formId}-buffer`}
            type="range"
            min={5}
            max={90}
            step={5}
            value={bufferMin}
            onChange={(e) => setBufferMin(Number(e.target.value))}
            className="mt-3 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-sky-400"
          />
        </Field>

        <button
          type="submit"
          disabled={loading}
          className="col-span-1 mt-2 flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-sky-500 to-blue-600 px-4 py-3 text-sm font-medium text-white shadow-lg shadow-blue-900/30 transition-all hover:from-sky-400 hover:to-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 disabled:cursor-not-allowed disabled:opacity-50 sm:col-span-2"
        >
          {loading ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              Checking connection…
            </>
          ) : (
            "Check my connection"
          )}
        </button>
      </form>

      {error && (
        <p role="alert" className="mt-4 rounded-lg bg-rose-500/10 px-4 py-3 text-sm text-rose-300 ring-1 ring-rose-500/30">
          {error}
        </p>
      )}

      {/* Result */}
      {result && riskStyle && (
        <div className="mt-8 space-y-6 border-t border-slate-700/40 pt-6">
          <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-start">
            <ProbabilityGauge probability={result.success_probability} color={riskStyle.ring} />

            <div className="flex-1 space-y-3 text-center sm:text-left">
              <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${riskStyle.badge}`}>
                {riskStyle.label}
              </span>
              <p className="text-sm leading-relaxed text-slate-300">{result.explanation}</p>

              <div className="grid grid-cols-2 gap-3 pt-1 text-left">
                <Stat
                  label={`${result.primary_train_number} predicted arrival`}
                  value={formatClock(result.primary_predicted_arrival)}
                />
                <Stat
                  label={`${result.connecting_train_number} departs`}
                  value={formatClock(result.connecting_scheduled_departure)}
                />
                <Stat
                  label="Effective buffer"
                  value={`${result.effective_buffer_min.toFixed(0)} min`}
                />
                <Stat
                  label="Your minimum"
                  value={`${result.required_buffer_min} min`}
                />
              </div>
            </div>
          </div>

          {result.alternative_trains.length > 0 && (
            <div>
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-[0.15em] text-slate-500">
                Alternative trains at {result.connection_station_code}
              </h3>
              <ul className="space-y-2">
                {result.alternative_trains.map((alt) => (
                  <li
                    key={alt.train_number}
                    className="flex items-center justify-between rounded-xl border border-slate-700/40 bg-slate-800/40 px-4 py-3"
                  >
                    <div>
                      <p className="text-sm font-medium text-slate-100">
                        {alt.train_name}
                        <span className="ml-2 font-mono text-xs text-slate-500">
                          #{alt.train_number}
                        </span>
                      </p>
                      <p className="text-xs text-slate-400">
                        Departs {formatClock(alt.departure_time)}
                      </p>
                    </div>
                    <span className="rounded-full bg-slate-700/60 px-2.5 py-1 font-mono text-xs tabular-nums text-slate-200">
                      {alt.success_probability.toFixed(0)}%
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Small presentational helpers
// ---------------------------------------------------------------------------

const inputClass =
  "mt-1.5 w-full rounded-lg border border-slate-700/60 bg-slate-800/60 px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 outline-none transition-colors focus:border-sky-400/60 focus:ring-1 focus:ring-sky-400/40";

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <label htmlFor={htmlFor} className="block text-xs font-medium text-slate-400">
      {label}
      {children}
    </label>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-800/50 px-3 py-2 ring-1 ring-slate-700/40">
      <p className="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="font-mono text-sm tabular-nums text-slate-100">{value}</p>
    </div>
  );
}
