"use client";

import clsx from "clsx";

export type CoachTab = "plan" | "planMoves" | "last" | "history" | "glossary" | "technical";

const TABS: Array<{ id: CoachTab; label: string }> = [
  { id: "plan", label: "Plan" },
  { id: "planMoves", label: "Coups du plan" },
  { id: "last", label: "Dernier coup" },
  { id: "history", label: "Historique" },
  { id: "glossary", label: "Glossaire" },
  { id: "technical", label: "Détails" }
];

export function CoachTabs({ activeTab, onChange }: { activeTab: CoachTab; onChange: (tab: CoachTab) => void }) {
  return (
    <div className="panel p-2">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            className={clsx(
              "min-h-10 rounded px-3 py-2 text-sm font-semibold transition",
              activeTab === tab.id ? "bg-night text-white" : "bg-stone-50 text-night hover:bg-white"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </div>
  );
}
