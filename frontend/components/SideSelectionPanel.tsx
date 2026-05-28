"use client";

import {
  COACH_STYLE_SETTINGS,
  HUMAN_PROFILE_SETTINGS,
  type CoachHumanProfile,
  type CoachStyle
} from "@/lib/eloAdaptation";
import { useState } from "react";

type SideSelectionPanelProps = {
  onChooseWhite: (profile: CoachHumanProfile, style: CoachStyle) => void;
  onChooseBlack: (profile: CoachHumanProfile, style: CoachStyle) => void;
  onChooseFreeMode: () => void;
};

export function SideSelectionPanel({ onChooseWhite, onChooseBlack, onChooseFreeMode }: SideSelectionPanelProps) {
  const [pendingSide, setPendingSide] = useState<"white" | "black" | null>(null);
  const [pendingProfile, setPendingProfile] = useState<CoachHumanProfile | null>(null);
  const profileEntries = Object.entries(HUMAN_PROFILE_SETTINGS) as Array<[CoachHumanProfile, (typeof HUMAN_PROFILE_SETTINGS)[CoachHumanProfile]]>;
  const styleEntries = Object.entries(COACH_STYLE_SETTINGS) as Array<[CoachStyle, (typeof COACH_STYLE_SETTINGS)[CoachStyle]]>;

  function chooseStyle(style: CoachStyle) {
    if (!pendingSide || !pendingProfile) return;
    if (pendingSide === "white") {
      onChooseWhite(pendingProfile, style);
    } else {
      onChooseBlack(pendingProfile, style);
    }
    setPendingSide(null);
    setPendingProfile(null);
  }

  function chooseProfile(profile: CoachHumanProfile) {
    setPendingProfile(profile);
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
        {pendingSide && pendingProfile ? (
          <div className="landing-profile-panel" aria-label="Choisir le style du coach">
            <h1>Style du coach</h1>
            <div className="landing-profile-grid">
              {styleEntries.map(([id, style]) => (
                <button key={id} type="button" className="landing-profile-choice" onClick={() => chooseStyle(id)} title={style.description}>
                  <span>{style.label}</span>
                  <strong>{style.shortLabel}</strong>
                </button>
              ))}
            </div>
            <button type="button" className="landing-profile-back" onClick={() => setPendingProfile(null)}>
              Retour
            </button>
          </div>
        ) : pendingSide ? (
          <div className="landing-profile-panel" aria-label="Choisir le style de coups">
            <h1>Style humain</h1>
            <div className="landing-profile-grid">
              {profileEntries.map(([id, profile]) => (
                <button key={id} type="button" className="landing-profile-choice" onClick={() => chooseProfile(id)} title={profile.description}>
                  <span>{profile.label}</span>
                  <strong>{profile.baseElo}</strong>
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
