import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PlanFirstPanel } from "./PlanFirstPanel";
import type { LivePlanInsightResponse, PlanEvent, PlanRecommendation, PlanRecommendationsResponse } from "@/lib/types";

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

const event: PlanEvent = {
  id: "opening-completed-caro",
  severity: "success",
  title: "Ouverture terminee",
  message: "On passe maintenant au plan de milieu de partie."
};

const insight: LivePlanInsightResponse = {
  headline: "Plan simple",
  currentPlan: "Finir le developpement sans forcer une attaque.",
  whyChanged: "La structure est stable et le centre est controle.",
  nextGoal: "Roquer puis placer une tour sur une colonne utile.",
  event: null,
  analysisProvider: "heuristic",
  analysisKind: "heuristic"
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
  pedagogicalSummary: "Tu suis la Caro-Kann.",
  moveComplexity: "simple",
  turnContext: {
    sideToMove: "black",
    planSide: "black",
    playerTurn: true,
    opponentTurn: false,
    gameOver: false
  },
  technicalDetails: {},
  technicalEngineMoves: []
};

describe("PlanFirstPanel", () => {
  it("shows the live plan instead of a move explanation in the cockpit", () => {
    render(<PlanFirstPanel recommendations={response} liveInsight={insight} />);
    expect(screen.getByText("Plan actuel")).toBeTruthy();
    expect(screen.getByText("Plan simple")).toBeTruthy();
    expect(screen.getByText("Finir le developpement sans forcer une attaque.")).toBeTruthy();
    expect(screen.getByText("Coup recommande")).toBeTruthy();
    expect(screen.getByText("Cavalier g8 -> f6")).toBeTruthy();
    expect(screen.queryByText("Focus plateau")).toBeNull();
  });

  it("keeps evaluation only inside advanced details", () => {
    render(<PlanFirstPanel recommendations={response} />);
    expect(screen.getByText("Details avances")).toBeTruthy();
    expect(screen.getByText("Evaluation : Position equilibree")).toBeTruthy();
    expect(screen.queryByText("Joue Cavalier g8 -> f6. Le cavalier controle le centre et garde le plan lisible.")).toBeNull();
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
          strategicPlan: {
            title: "Observer la reponse adverse",
            goal: "Regarder la reponse noire.",
            reason: "C'est a l'autre camp de jouer.",
            nextObjective: "Adapter le plan ensuite."
          },
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
    expect(screen.queryByText("Aucun coup de plan clair. Joue un coup legal simple ou consulte les details.")).toBeNull();
  });

  it("shows ranked choices and event feed after the opening", () => {
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
        events={[event]}
      />
    );
    expect(screen.getByText("Choix strategiques")).toBeTruthy();
    expect(screen.getByText("Meilleur")).toBeTruthy();
    expect(screen.getByText("Alternative saine")).toBeTruthy();
    expect(screen.getByText("Ouverture terminee")).toBeTruthy();
  });
});
