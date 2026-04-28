export type Orientation = "white" | "black";
export type PlayMode = "both" | "white" | "black" | "friend";
export type SkillLevel = "beginner" | "intermediate" | "pro";
export type Difficulty = "easy" | "medium" | "hard";
export type Risk = "low" | "medium" | "high";

export type CandidateMove = {
  rank: number;
  moveUci: string;
  moveSan: string;
  stockfishRank: number;
  evalCp: number | null;
  mateIn: number | null;
  pv: string[];
  coachScore: number;
  engineScore: number;
  humanLikelihood: number;
  simplicityScore: number;
  riskPenalty: number;
  difficulty: Difficulty;
  risk: Risk;
  summary: string;
};

export type AnalyzeResponse = {
  fen: string;
  elo: number;
  sideToMove: "white" | "black";
  candidates: CandidateMove[];
};

export type ExplainResponse = {
  title: string;
  moveLabel: string;
  oneSentence: string;
  sections: {
    whatToDo: string;
    mainIdea: string;
    whyNow: string;
    whatItProvokes: string;
    nextPlan: string[];
    danger: string;
    commonMistake: string;
    betterThan: string;
  };
  technical: {
    san: string;
    uci: string;
    evalCp: number | null;
    pv: string[];
  };
  translatedPv: Array<{
    moveNumber: number;
    side: "white" | "black";
    beginnerLabel: string;
    simpleExplanation: string;
  }>;
};

export type ReviewMoveResponse = {
  moveLabel: string;
  coachNarrative: string;
  analysisProvider: "heuristic" | "openai" | "gemini" | "ollama";
  analysisKind: "ai" | "heuristic";
  quality: "excellent" | "good" | "playable" | "inaccurate" | "mistake" | "blunder";
  qualityLabel: string;
  playedMoveEvalLabel: string;
  bestMoveLabel: string;
  bestMoveWasDifferent: boolean;
  explanation: {
    probableIdea: string;
    whatItDoes: string;
    whatItAllows: string;
    whatToWatch: string;
    comparisonWithBest: string;
  };
  connectionToPlan?: string | null;
  whatItAttacks?: string[];
  whatItDefends?: string[];
  whatItAllowsNext?: string[];
  bestAlternative?: {
    moveLabel: string;
    whyBetterOrDifferent: string;
  } | null;
  warning?: string | null;
};

export type BotMoveResponse = {
  move: CandidateMove;
  selectionReason: string;
  updatedStrategyState: Record<string, unknown>;
  explanationPreview: string;
};

export type PositionPlanResponse = {
  phase: "opening" | "middlegame" | "endgame";
  phaseLabel: string;
  detectedOpening: {
    id: string;
    name: string;
    beginnerGoal: string;
    mainIdeas: string[];
    whatToAvoid: string[];
  } | null;
  plan: string[];
  nextObjective: string;
  positionContext: {
    phase: string;
    centerPawns: string;
    kingSafety: string;
    undevelopedPieces: string[];
    importantSquares: string[];
  };
};

export type StrategyPlan = {
  id: string;
  nameFr: string;
  nameEn: string;
  side: "white" | "black" | "universal";
  against: string[];
  tier: "recommended" | "good" | "situational" | "hidden";
  difficulty: "easy" | "medium" | "hard";
  style: string[];
  recommendedElo: [number, number];
  mainLineUci: string[];
  eco: string[];
  beginnerGoal: string;
  coreIdeas: string[];
  pieceMissions: Array<{ piece: string; mission: string }>;
  heroImage?: string | null;
  miniBoardFen?: string;
  shortHistory?: string;
  learningGoal?: string;
  successCriteria?: string[];
  middlegamePlan?: string[];
  endgamePlan?: string[];
  whatYouWillLearn?: string[];
};

export type PlanRecommendation = {
  moveUci: string;
  moveSan: string;
  beginnerLabel: string;
  source: "plan" | "engine" | "plan_and_engine" | "fallback_principle";
  engineRank: number | null;
  planRank: number | null;
  planFitScore: number;
  engineScore: number;
  beginnerSimplicityScore: number;
  tacticalRisk: number;
  finalCoachScore: number;
  evalLabel: string;
  purpose: string;
  planConnection: string;
  pedagogicalExplanation?: string;
  moveComplexity?: "simple" | "moyen" | "complexe";
  warning: string | null;
  candidate: CandidateMove | null;
  displayRank?: number;
  displayRole?: string;
  arrowColor?: string;
};

export type GamePlanState = {
  selectedPlanId: string | null;
  planName: string | null;
  side: string | null;
  phase: "opening" | "transition" | "middlegame" | "endgame";
  status: "on_plan" | "transposed" | "opponent_deviated" | "out_of_book" | "plan_completed";
  currentStepIndex: number;
  currentGoals: string[];
  nextObjectives: string[];
  knownOpponentDeviation: Record<string, unknown> | null;
  recommendedPlanMoves: string[];
  fallbackPrinciples: string[];
  engineSafetyWarning: string | null;
  statusExplanation: string;
};

export type PlanRecommendationsResponse = {
  planState: GamePlanState;
  planMoves: PlanRecommendation[];
  engineMoves: CandidateMove[];
  mergedRecommendations: PlanRecommendation[];
  explanationContext: Record<string, unknown>;
  selectedPlan: StrategyPlan | null;
  phase: "opening" | "transition" | "middlegame" | "endgame";
  phaseDisplay: {
    key: "opening" | "middlegame" | "endgame";
    label: string;
    subtitle: string;
    recommendationStyle: "single" | "ranked" | "conversion";
    maxVisibleMoves: number;
  };
  phaseStatus: string;
  planProgress: {
    percent?: number;
    completed?: number;
    total?: number;
    criteria?: Array<{ label: string; ok: boolean }>;
    linePly?: number;
    lineTotal?: number;
    tempoPly?: number;
    tempoTotal?: number;
  };
  currentObjective: string;
  lastEvent?: string;
  whatChanged?: string;
  nextObjective?: string;
  recommendedPlanMoves?: PlanRecommendation[];
  primaryMove: PlanRecommendation | null;
  expectedOpponentMove: PlanRecommendation | null;
  adaptedAlternatives: PlanRecommendation[];
  blockedExpectedMove: {
    moveUci: string;
    beginnerLabel: string;
    reason: string;
    deviation?: Record<string, unknown> | null;
  } | null;
  coachMessage: string;
  pedagogicalSummary?: string;
  moveComplexity?: "simple" | "moyen" | "complexe";
  technicalDetails?: Record<string, unknown>;
  technicalEngineMoves: CandidateMove[];
};
