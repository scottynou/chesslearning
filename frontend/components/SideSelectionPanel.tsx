"use client";

type SideSelectionPanelProps = {
  onChooseWhite: () => void;
  onChooseBlack: () => void;
  onChooseFreeMode: () => void;
};

export function SideSelectionPanel({ onChooseWhite, onChooseBlack, onChooseFreeMode }: SideSelectionPanelProps) {
  return (
    <section className="landing-shell">
      <div className="landing-brand">
        <span>Chess Learning</span>
      </div>

      <div className="landing-choice-grid" aria-label="Choisir un camp">
        <SideButton label="Je joue les blancs" tone="light" onClick={onChooseWhite} />
        <SideButton label="Je joue les noirs" tone="dark" onClick={onChooseBlack} />
      </div>

      <button type="button" onClick={onChooseFreeMode} className="landing-free-button">
        Mode libre
      </button>
    </section>
  );
}

function SideButton({ label, tone, onClick }: { label: string; tone: "light" | "dark"; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={tone === "dark" ? "landing-side-button is-dark" : "landing-side-button"}>
      <span>{label}</span>
    </button>
  );
}
