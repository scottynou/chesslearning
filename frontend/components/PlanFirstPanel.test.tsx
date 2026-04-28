import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
  pedagogicalExplanation: "Texte cache.",
  moveComplexity: "simple",
  warning: null,
  candidate: null,
  displayRole: "Coup du plan",
  arrowColor: "rgba(224,185,118,0.78)"
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
  openingState: "on_track",
  phaseReason: "Le plan avance normalement.",
  planEvent: null,
  strategicPlan: {
    title: "Caro-Kann",
    goal: "Installer c6 puis d5.",
    reason: "Le plan est encore coherent.",
    nextObjective: "Developper une piece."
  },
  planProgress: { percent: 25, impact: "Ce coup fait avancer la ligne principale de l'ouverture." },
  openingBrief: {
    summary: "Caro-Kann consiste a repondre a e4 avec c6 puis d5.",
    completion: "Terminee lorsque c6 et d5 sont installes."
  },
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
  pedagogicalSummary: "Texte cache.",
  moveComplexity: "simple",
  turnContext: {
    sideToMove: "black",
    planSide: "black",
    playerTurn: true,
    opponentTurn: false,
    gameOver: false
  },
  aiRerankStatus: {
    provider: "local",
    model: null,
    status: "disabled",
    latencyMs: 0,
    fallbackReason: "not_enough_choices"
  },
  adaptiveSignal: {
    pressure: "stable",
    suggestedBoostDelta: 0,
    reason: "stable"
  },
  technicalDetails: {},
  technicalEngineMoves: []
};

describe("PlanFirstPanel", () => {
  it("shows only phase, progress and useful moves", () => {
    render(<PlanFirstPanel recommendations={response} />);
    expect(screen.getByText("Coups")).toBeTruthy();
    expect(screen.getAllByText("Ouverture").length).toBeGreaterThan(0);
    expect(screen.getAllByText("25%").length).toBeGreaterThan(0);
    expect(screen.getByText("Coup recommande")).toBeTruthy();
    expect(screen.getByText("Cavalier g8 -> f6")).toBeTruthy();
    expect(screen.queryByText("Plan actuel")).toBeNull();
    expect(screen.queryByText("Details avances")).toBeNull();
    expect(screen.queryByText("Texte cache.")).toBeNull();
  });

  it("does not turn an opponent reply into the player's recommendation", () => {
    render(
      <PlanFirstPanel
        recommendations={{
          ...response,
          primaryMove: null,
          planMoves: [],
          mergedRecommendations: [],
          expectedOpponentMove: recommendation,
          turnContext: {
            ...response.turnContext,
            sideToMove: "white",
            playerTurn: false,
            opponentTurn: true
          }
        }}
      />
    );
    expect(screen.getAllByText("Coup adverse attendu").length).toBeGreaterThan(0);
    expect(screen.getByText("Cavalier g8 -> f6")).toBeTruthy();
    expect(screen.queryByText("Aucun coup legal disponible.")).toBeNull();
  });

  it("shows ranked choices after the opening", () => {
    const alternative = { ...recommendation, moveUci: "b8c6", beginnerLabel: "Cavalier b8 -> c6", displayRole: "Alternative saine" };
    const primary = { ...recommendation, displayRole: "Meilleur" };
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
          openingState: "completed",
          primaryMove: primary,
          mergedRecommendations: [primary, alternative],
          adaptedAlternatives: [alternative]
        }}
      />
    );
    expect(screen.getByText("Coups proposes")).toBeTruthy();
    expect(screen.getByText("Meilleur")).toBeTruthy();
    expect(screen.getByText("Alternative saine")).toBeTruthy();
    expect(screen.queryByText("Ouverture terminee")).toBeNull();
  });
});
