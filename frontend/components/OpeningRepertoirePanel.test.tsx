import { render, screen } from "@testing-library/react";
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

describe("OpeningRepertoirePanel", () => {
  it("shows opening plan cards clearly", () => {
    render(<OpeningRepertoirePanel plans={[plan]} selectedPlanId={null} onSelect={() => undefined} />);
    expect(screen.getByText("Choisis ton plan")).toBeTruthy();
    expect(screen.getByText("Caro-Kann")).toBeTruthy();
    expect(screen.getByText("Intermediaire")).toBeTruthy();
    expect(screen.getByText("Comprendre ce plan")).toBeTruthy();
  });
});
