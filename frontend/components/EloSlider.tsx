"use client";

import { ELO_STEPS } from "@/lib/elo";

type EloSliderProps = {
  value: number;
  onChange: (value: number) => void;
};

export function EloSlider({ value, onChange }: EloSliderProps) {
  const index = ELO_STEPS.indexOf(value as (typeof ELO_STEPS)[number]);

  return (
    <label className="grid gap-2">
      <span className="flex items-center justify-between text-sm font-medium text-night">
        Elo coach
        <span className="rounded bg-night px-2 py-1 text-xs text-white">{value}</span>
      </span>
      <input
        aria-label="Elo coach"
        type="range"
        min={0}
        max={ELO_STEPS.length - 1}
        step={1}
        value={Math.max(0, index)}
        onChange={(event) => onChange(ELO_STEPS[Number(event.target.value)])}
        className="accent-clay"
      />
      <div className="flex justify-between text-[11px] text-neutral-500">
        <span>600</span>
        <span>1600</span>
        <span>2400</span>
        <span>3200</span>
      </div>
    </label>
  );
}
