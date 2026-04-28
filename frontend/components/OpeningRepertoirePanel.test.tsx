import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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
  it("shows minimal opening plan cards", () => {
    render(<OpeningRepertoirePanel plans={[plan]} selectedPlanId={null} onSelect={() => undefined} />);

    expect(screen.getByText("Choisis ton plan")).toBeTruthy();
    expect(screen.getByText("Caro-Kann")).toBeTruthy();
    expect(screen.getByText("Intermediaire")).toBeTruthy();
    expect(screen.queryByText("Recommande")).toBeNull();
    expect(screen.queryByText("Comprendre ce plan")).toBeNull();
  });

  it("shows black reply cards as concise reasons", () => {
    render(<OpeningRepertoirePanel plans={[plan]} selectedPlanId={null} onSelect={() => undefined} mode="black-reply" firstMoveLabel="Nf3" />);

    expect(screen.getByText("Caro-Kann")).toBeTruthy();
    expect(screen.getByText("Reponse")).toBeTruthy();
    expect(screen.getByText(/Apres Nf3/)).toBeTruthy();
    expect(screen.queryByText("Comprendre cette reponse")).toBeNull();
  });

  it("selects a plan directly from the card", () => {
    const onSelect = vi.fn();

    render(<OpeningRepertoirePanel plans={[plan, secondPlan]} selectedPlanId={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: /Partie italienne/i }));

    expect(onSelect).toHaveBeenCalledWith("italian_game_beginner");
  });
});
