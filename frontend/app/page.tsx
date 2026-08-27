"use client";

import { useState } from "react";
import Navbar from "@/components/Navbar";
import LiveEtaTracker from "@/components/LiveEtaTracker";
import ConnectionChecker from "@/components/ConnectionChecker";
import WhatIfSimulator from "@/components/WhatIfSimulator";
import DispatcherDashboard from "@/components/DispatcherDashboard";

type TabType = "eta" | "connection" | "whatif" | "dispatcher";

export default function Page() {
  const [activeTab, setActiveTab] = useState<TabType>("eta");

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-sky-500 selection:text-white">
      {/* Top Navbar */}
      <Navbar activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* Main Content Area */}
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {activeTab === "eta" && <LiveEtaTracker />}
        {activeTab === "connection" && (
          <div className="mx-auto max-w-4xl space-y-6">
            <div className="text-center">
              <span className="text-xs font-semibold uppercase tracking-[0.25em] text-sky-400">
                Risk Engine
              </span>
              <h2 className="mt-1 text-2xl font-bold tracking-tight text-slate-50 sm:text-3xl">
                Connecting Train Risk & Alternative Rerouting
              </h2>
            </div>
            <ConnectionChecker />
          </div>
        )}
        {activeTab === "whatif" && <WhatIfSimulator />}
        {activeTab === "dispatcher" && <DispatcherDashboard />}
      </main>
    </div>
  );
}
