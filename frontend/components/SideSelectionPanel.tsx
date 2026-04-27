"use client";

type SideSelectionPanelProps = {
  onChooseWhite: () => void;
  onChooseBlack: () => void;
  onChooseFreeMode: () => void;
};

export function SideSelectionPanel({ onChooseWhite, onChooseBlack, onChooseFreeMode }: SideSelectionPanelProps) {
  const boardCells = Array.from({ length: 64 }, (_, index) => index);

  return (
    <section className="landing-shell">
      <div className="landing-hero">
        <div className="landing-copy">
          <p className="landing-kicker">Coach d&apos;ouverture plan-first</p>
          <h1 className="landing-title">Choisis ton camp. Le plan vient ensuite.</h1>
          <p className="landing-subtitle">
            Une interface pour jouer sur ton echiquier interne, comprendre l&apos;idee du plan, puis t&apos;adapter sans te perdre dans une liste moteur.
          </p>
        </div>

        <div className="landing-visual" aria-hidden="true">
          <div className="landing-board-art">
            {boardCells.map((cell) => (
              <span key={cell} className={(Math.floor(cell / 8) + cell) % 2 === 0 ? "landing-board-cell" : "landing-board-cell is-dark"} />
            ))}
          </div>
          <div className="landing-line one" />
          <div className="landing-line two" />
          <div className="landing-piece-mark king">K</div>
          <div className="landing-piece-mark knight">N</div>
        </div>
      </div>

      <div className="landing-decision-panel">
        <div className="landing-choice-grid" aria-label="Choisir un camp">
          <SideButton label="Je joue les blancs" meta="Construire ton ouverture et forcer les premiers objectifs." tone="light" onClick={onChooseWhite} />
          <SideButton label="Je joue les noirs" meta="Entrer le premier coup blanc, puis choisir la meilleure reponse." tone="dark" onClick={onChooseBlack} />
        </div>

        <button type="button" onClick={onChooseFreeMode} className="landing-free-button">
          Mode libre
        </button>
      </div>
    </section>
  );
}

function SideButton({ label, meta, tone, onClick }: { label: string; meta: string; tone: "light" | "dark"; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className={tone === "dark" ? "landing-side-button is-dark" : "landing-side-button"}>
      <span>{label}</span>
      <small>{meta}</small>
    </button>
  );
}
