"use client";

import { ChevronRight } from "lucide-react";

type SideSelectionPanelProps = {
  onChooseWhite: () => void;
  onChooseBlack: () => void;
  onChooseFreeMode: () => void;
};

export function SideSelectionPanel({ onChooseWhite, onChooseBlack, onChooseFreeMode }: SideSelectionPanelProps) {
  return (
    <section className="grid gap-5">
      <div className="grid gap-2">
        <p className="text-sm font-semibold uppercase text-clay">Chess Elo Coach</p>
        <h1 className="max-w-3xl text-3xl font-bold text-ink sm:text-5xl">Tu veux apprendre avec les blancs ou les noirs ?</h1>
        <p className="max-w-2xl text-sm leading-6 text-neutral-700">
          Choisis ton camp, puis le coach te guide dans un plan clair. Le but n&apos;est pas de recopier Stockfish : c&apos;est de comprendre quoi jouer, pourquoi, et comment adapter le plan.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <button type="button" onClick={onChooseWhite} className="group rounded-lg border border-line bg-white p-5 text-left shadow-soft transition hover:-translate-y-0.5 hover:border-sage">
          <div className="flex items-center justify-between gap-3">
            <span className="text-2xl font-bold text-night">Je joue les blancs</span>
            <ChevronRight className="text-clay transition group-hover:translate-x-1" size={22} />
          </div>
          <p className="mt-3 text-sm leading-6 text-neutral-700">
            Tu choisis directement une ouverture blanche, puis tu suis le plan coup par coup.
          </p>
        </button>

        <button type="button" onClick={onChooseBlack} className="group rounded-lg border border-line bg-night p-5 text-left text-white shadow-soft transition hover:-translate-y-0.5 hover:border-clay">
          <div className="flex items-center justify-between gap-3">
            <span className="text-2xl font-bold">Je joue les noirs</span>
            <ChevronRight className="text-clay transition group-hover:translate-x-1" size={22} />
          </div>
          <p className="mt-3 text-sm leading-6 text-stone-100">
            Tu entres d&apos;abord le premier coup blanc sur l&apos;echiquier, puis le coach propose les reponses adaptees.
          </p>
        </button>
      </div>

      <button type="button" onClick={onChooseFreeMode} className="w-fit rounded border border-line bg-white px-3 py-2 text-sm font-semibold text-night hover:border-sage">
        Mode libre / jouer les deux camps
      </button>
    </section>
  );
}
