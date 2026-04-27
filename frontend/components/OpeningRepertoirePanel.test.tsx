import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { OpeningRepertoirePanel } from "./OpeningRepertoirePanel";
import type { StrategyPlan } from "@/lib/types";

const plan: StrategyPlan = {
  id: "caro_kann_beginner",
  nameFr: "Caro-Kann",
  nameEn: "Caro-Kann Defense",
  side: "black",
  against: ["e2e4"],
  tier: "recommended",
  difficulty: "medium",
  style: ["solide", "centre"],
  recommendedElo: [600, 2200],
  mainLineUci: ["e2e4", "c7c6"],
  eco: ["B10"],
  beginnerGoal: "Attaquer le centre blanc avec une structure solide.",
  coreIdeas: ["Attaquer le centre.", "Developper les pieces.", "Roquer."],
  pieceMissions: [],
  miniBoardFen: "rnbqkbnr/pp1ppppp/2p5/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
  whatYouWillLearn: ["Attaquer le centre", "Construire une structure", "Passer au milieu de partie"]
};

const secondPlan: StrategyPlan = {
  ...plan,
  id: "italian_game_beginner",
  nameFr: "Partie italienne",
  difficulty: "easy",
  style: ["classique"],
  mainLineUci: ["e2e4", "e7e5", "g1f3"],
  beginnerGoal: "Developper vite les pieces et roquer.",
  coreIdeas: ["Prendre le centre.", "Developper les pieces.", "Roquer vite."],
  whatYouWillLearn: ["Developper avant d'attaquer", "Viser f7", "Roquer"]
};

describe("OpeningRepertoirePanel", () => {
  it("shows opening plan cards clearly", () => {
    render(<OpeningRepertoirePanel plans={[plan]} selectedPlanId={null} onSelect={() => undefined} />);
    expect(screen.getByText("Choisis ton plan")).toBeTruthy();
    expect(screen.getByText("Caro-Kann")).toBeTruthy();
    expect(screen.getByText("Intermediaire")).toBeTruthy();
    expect(screen.getByText("Comprendre ce plan")).toBeTruthy();
  });

  it("shows black reply cards as concise reasons", () => {
    render(<OpeningRepertoirePanel plans={[plan]} selectedPlanId={null} onSelect={() => undefined} mode="black-reply" firstMoveLabel="Nf3" />);
    expect(screen.getByText("Caro-Kann")).toBeTruthy();
    expect(screen.getByText("Pourquoi ici")).toBeTruthy();
    expect(screen.getByText(/milieu de partie clair/)).toBeTruthy();
    expect(screen.getByText("Comprendre cette reponse")).toBeTruthy();
  });

  it("keeps multiple opening explanations expanded until each one is hidden", () => {
    render(<OpeningRepertoirePanel plans={[plan, secondPlan]} selectedPlanId={null} onSelect={() => undefined} />);
    const buttons = screen.getAllByText("Comprendre ce plan");
    fireEvent.click(buttons[0]);
    fireEvent.click(buttons[1]);
    expect(screen.getAllByText("Ce que tu vas apprendre")).toHaveLength(2);
    fireEvent.click(screen.getAllByText("Masquer")[0]);
    expect(screen.getAllByText("Ce que tu vas apprendre")).toHaveLength(1);
  });
});
