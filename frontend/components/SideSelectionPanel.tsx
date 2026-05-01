"use client";

import { HUMAN_PROFILE_SETTINGS, type CoachHumanProfile } from "@/lib/eloAdaptation";
import { useState } from "react";

type SideSelectionPanelProps = {
  onChooseWhite: (profile: CoachHumanProfile) => void;
  onChooseBlack: (profile: CoachHumanProfile) => void;
  onChooseFreeMode: () => void;
};

export function SideSelectionPanel({ onChooseWhite, onChooseBlack, onChooseFreeMode }: SideSelectionPanelProps) {
  const [pendingSide, setPendingSide] = useState<"white" | "black" | null>(null);
  const profileEntries = Object.entries(HUMAN_PROFILE_SETTINGS) as Array<[CoachHumanProfile, (typeof HUMAN_PROFILE_SETTINGS)[CoachHumanProfile]]>;

  function chooseProfile(profile: CoachHumanProfile) {
    if (pendingSide === "white") {
      onChooseWhite(profile);
      return;
    }
    if (pendingSide === "black") {
      onChooseBlack(profile);
    }
  }

  return (
    <section className="landing-shell" aria-label="Choisir un mode de jeu">
      <div className="landing-backdrop" aria-hidden="true">
        <picture>
          <source media="(max-width: 700px)" srcSet="./landing/chessboard-luxe-bg-mobile.png" />
          <img className="landing-backdrop-image" src="./landing/chessboard-luxe-bg-desktop.png" alt="" />
        </picture>
      </div>

      <div className="landing-decision-panel">
        {pendingSide ? (
          <div className="landing-profile-panel" aria-label="Choisir le style de coups">
            <h1>Style humain</h1>
            <div className="landing-profile-grid">
              {profileEntries.map(([id, profile]) => (
                <button key={id} type="button" className="landing-profile-choice" onClick={() => chooseProfile(id)}>
                  <span>{profile.label}</span>
                  <strong>{profile.baseElo}</strong>
                  <em>{profile.description}</em>
                </button>
              ))}
            </div>
            <button type="button" className="landing-profile-back" onClick={() => setPendingSide(null)}>
              Retour
            </button>
          </div>
        ) : (
          <>
            <h1 className="sr-only">Choisis ton camp</h1>
            <div className="landing-choice-grid" aria-label="Choisir un camp">
              <SideButton label="Blancs" accessibleLabel="Je joue les blancs" tone="light" onClick={() => setPendingSide("white")} />
              <SideButton label="Noirs" accessibleLabel="Je joue les noirs" tone="dark" onClick={() => setPendingSide("black")} />
            </div>

            <button type="button" onClick={onChooseFreeMode} className="landing-free-button">
              Mode libre
            </button>
          </>
        )}
      </div>
    </section>
  );
}

function SideButton({ label, accessibleLabel, tone, onClick }: { label: string; accessibleLabel: string; tone: "light" | "dark"; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={tone === "dark" ? "landing-side-button is-dark" : "landing-side-button"} aria-label={accessibleLabel}>
      <span>{label}</span>
    </button>
  );
}
