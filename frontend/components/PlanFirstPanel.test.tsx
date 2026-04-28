import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PlanFirstPanel } from "./PlanFirstPanel";
import type { PlanRecommendation, PlanRecommendationsResponse } from "@/lib/types";

const recommendation: PlanRecommendation = {
  moveUci: "g8f6",
  moveSan: "Nf6",
  beginnerLabel: "Cavalier g8 -> f6",
  source: "plan_and_engine",
  engineRank: 2,
  planRank: 1,
  planFitScore: 92,
  engineScore: 84,
  beginnerSimplicityScore: 78,
  tacticalRisk: 12,
  finalCoachScore: 89,
  evalLabel: "Position equilibree",
  purpose: "Developper le cavalier vers f6.",
  planConnection: "Ce coup suit le plan.",
  pedagogicalExplanation: "Joue Cavalier g8 -> f6. Le cavalier controle le centre et garde le plan lisible.",
  moveComplexity: "simple",
  warning: null,
  candidate: null
};

const response: PlanRecommendationsResponse = {
  planState: {
    selectedPlanId: "caro_kann_beginner",
    planName: "Caro-Kann",
    side: "black",
    phase: "opening",
    status: "on_plan",
    currentStepIndex: 1,
    currentGoals: [],
    nextObjectives: [],
    knownOpponentDeviation: null,
    recommendedPlanMoves: ["g8f6"],
    fallbackPrinciples: [],
    engineSafetyWarning: null,
    statusExplanation: "Tu suis le plan."
  },
  planMoves: [recommendation],
  engineMoves: [],
  mergedRecommendations: [recommendation],
  explanationContext: {},
  selectedPlan: null,
  phase: "opening",
  phaseDisplay: {
    key: "opening",
    label: "Ouverture",
    subtitle: "Un seul coup pour accomplir ton plan.",
    recommendationStyle: "single",
    maxVisibleMoves: 1
  },
  phaseStatus: "opening_in_progress",
  planProgress: { percent: 25 },
  currentObjective: "Developper une piece.",
  lastEvent: "Les blancs viennent de jouer Pion e2 -> e4.",
  whatChanged: "Le plan reste coherent.",
  nextObjective: "Developper une piece.",
  recommendedPlanMoves: [recommendation],
  primaryMove: recommendation,
  expectedOpponentMove: null,
  adaptedAlternatives: [],
  blockedExpectedMove: null,
  coachMessage: "Tu suis la Caro-Kann.",
  pedagogicalSummary: "Tu suis la Caro-Kann.",
  moveComplexity: "simple",
  technicalDetails: {},
  technicalEngineMoves: []
};

describe("PlanFirstPanel", () => {
  it("shows the educational explanation directly in the move card", () => {
    render(<PlanFirstPanel recommendations={response} onToggleRecommendation={() => undefined} highlightedMoveUci="g8f6" expectedReplyLabel="Pion d2 -> d4" />);
    expect(screen.getByText("Dernier fait")).toBeTruthy();
    expect(screen.getByText("Reponse attendue")).toBeTruthy();
    expect(screen.getByText("Joue Cavalier g8 -> f6. Le cavalier controle le centre et garde le plan lisible.")).toBeTruthy();
    expect(screen.queryByText("Comprendre ce coup")).toBeNull();
  });

  it("highlights a recommendation on demand without opening a separate explanation panel", () => {
    const onSelect = vi.fn();
    render(<PlanFirstPanel recommendations={response} onToggleRecommendation={onSelect} highlightedMoveUci={null} />);
    fireEvent.click(screen.getByText("Focus plateau"));
    expect(onSelect).toHaveBeenCalledWith(recommendation);
  });

  it("does not turn an opponent reply into the player's recommendation", () => {
    render(
      <PlanFirstPanel
        recommendations={{ ...response, primaryMove: null, planMoves: [], expectedOpponentMove: recommendation }}
        onToggleRecommendation={() => undefined}
        highlightedMoveUci={null}
      />
    );
    expect(screen.queryByText("Focus plateau")).toBeNull();
    expect(screen.getByText("A l'adversaire de jouer. Ligne attendue : Cavalier g8 -> f6.")).toBeTruthy();
  });

  it("shows ranked choices after the opening", () => {
    const alternative = { ...recommendation, moveUci: "b8c6", beginnerLabel: "Cavalier b8 -> c6", displayRole: "Alternative saine" };
    render(
      <PlanFirstPanel
        recommendations={{
          ...response,
          phase: "middlegame",
          phaseDisplay: {
            key: "middlegame",
            label: "Milieu de partie",
            subtitle: "Choisis un plan humain.",
            recommendationStyle: "ranked",
            maxVisibleMoves: 3
          },
          primaryMove: { ...recommendation, displayRole: "Meilleur" },
          adaptedAlternatives: [alternative]
        }}
        onToggleRecommendation={() => undefined}
        highlightedMoveUci={null}
      />
    );
    expect(screen.getByText("Choix strategiques")).toBeTruthy();
    expect(screen.getByText("Meilleur")).toBeTruthy();
    expect(screen.getByText("Alternative saine")).toBeTruthy();
  });
});
