"use client";

type TabType = "eta" | "connection" | "whatif" | "dispatcher";

interface NavbarProps {
  activeTab: TabType;
  setActiveTab: (tab: TabType) => void;
}

export default function Navbar({ activeTab, setActiveTab }: NavbarProps) {
  const navItems: { id: TabType; label: string; icon: string }[] = [
    { id: "eta", label: "Live ETA & SHAP", icon: "🚆" },
    { id: "connection", label: "Connection Risk", icon: "🔗" },
    { id: "whatif", label: "What-If Simulator", icon: "⚡" },
    { id: "dispatcher", label: "Network Dashboard", icon: "📊" },
  ];

  return (
    <header className="sticky top-0 z-50 w-full border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-4 py-3 sm:flex-row sm:px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-sky-400 to-blue-600 shadow-md shadow-sky-500/20 ring-1 ring-sky-300/30">
            <span className="text-lg">⚡</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold tracking-tight text-slate-100">YatraFlux AI</h1>
              <span className="rounded-full bg-sky-500/10 px-2 py-0.5 text-[10px] font-semibold text-sky-400 ring-1 ring-sky-500/30">
                LightGBM + SHAP
              </span>
            </div>
            <p className="text-[11px] text-slate-400">Predictive Railway Intelligence Platform</p>
          </div>
        </div>

        <nav className="flex flex-wrap items-center justify-center gap-1.5 rounded-2xl border border-slate-800 bg-slate-900/80 p-1.5 backdrop-blur-md">
          {navItems.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`flex items-center gap-2 rounded-xl px-3.5 py-2 text-xs font-medium transition-all ${
                  isActive
                    ? "bg-gradient-to-r from-sky-500 to-blue-600 text-white shadow-md shadow-blue-500/25 ring-1 ring-sky-300/40"
                    : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
                }`}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
