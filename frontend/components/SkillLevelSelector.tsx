"use client";

import clsx from "clsx";
import { SKILL_LEVELS } from "@/lib/skillLevel";
import type { SkillLevel } from "@/lib/types";

type SkillLevelSelectorProps = {
  value: SkillLevel;
  onChange: (value: SkillLevel) => void;
};

export function SkillLevelSelector({ value, onChange }: SkillLevelSelectorProps) {
  return (
    <div className="grid gap-2">
      <p className="text-sm font-semibold text-night">Niveau du coach</p>
      <div className="grid gap-2 sm:grid-cols-3">
        {SKILL_LEVELS.map((level) => (
          <button
            key={level.id}
            type="button"
            onClick={() => onChange(level.id)}
            className={clsx(
              "rounded border px-3 py-3 text-left transition",
              value === level.id ? "border-clay bg-orange-50 text-night" : "border-line bg-white text-neutral-700 hover:border-sage"
            )}
          >
            <span className="block text-sm font-semibold">{level.label}</span>
            <span className="mt-1 block text-xs leading-5">{level.description}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
