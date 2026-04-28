"use client";

type SideSelectionPanelProps = {
  onChooseWhite: () => void;
  onChooseBlack: () => void;
  onChooseFreeMode: () => void;
};

export function SideSelectionPanel({ onChooseWhite, onChooseBlack, onChooseFreeMode }: SideSelectionPanelProps) {
  return (
    <section className="landing-shell" aria-label="Choisir un mode de jeu">
      <div className="landing-backdrop" aria-hidden="true">
        <picture>
          <source media="(max-width: 700px)" srcSet="./landing/chessboard-luxe-bg-mobile.png" />
          <img className="landing-backdrop-image" src="./landing/chessboard-luxe-bg-desktop.png" alt="" />
        </picture>
      </div>

      <div className="landing-decision-panel">
        <h1 className="sr-only">Choisis ton camp</h1>
        <div className="landing-choice-grid" aria-label="Choisir un camp">
          <SideButton label="Blancs" accessibleLabel="Je joue les blancs" tone="light" onClick={onChooseWhite} />
          <SideButton label="Noirs" accessibleLabel="Je joue les noirs" tone="dark" onClick={onChooseBlack} />
        </div>

        <button type="button" onClick={onChooseFreeMode} className="landing-free-button">
          Mode libre
        </button>
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
