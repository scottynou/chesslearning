import type {
  AnalyzeResponse,
  BotMoveResponse,
  CandidateMove,
  ExplainResponse,
  PlanRecommendationsResponse,
  PositionPlanResponse,
  ReviewMoveResponse,
  SkillLevel,
  StrategyPlan
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function requestJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      // Keeps cross-origin POSTs CORS-simple; the API maps this body back to JSON.
      "Content-Type": "text/plain"
    },
    body: JSON.stringify(body)
  });

  if (!response.ok) {
    let message = "Le backend n'a pas répondu correctement.";
    try {
      const data = await response.json();
      message = typeof data.detail === "string" ? data.detail : message;
    } catch {
      message = response.statusText || message;
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(response.statusText || "Le backend n'a pas répondu correctement.");
  }
  return response.json() as Promise<T>;
}

export function analyzePosition(fen: string, elo: number, maxMoves: number, engineDepth = 14): Promise<AnalyzeResponse> {
  return requestJson<AnalyzeResponse>("/analyze", {
    fen,
    elo,
    maxMoves,
    engineDepth
  });
}

export function explainMove(params: {
  fen: string;
  elo: number;
  selectedMove: CandidateMove;
  allCandidates: CandidateMove[];
  moveHistoryPgn?: string;
  beginnerMode?: boolean;
}): Promise<ExplainResponse> {
  return requestJson<ExplainResponse>("/explain-candidate", {
    ...params,
    beginnerMode: params.beginnerMode ?? true
  });
}

export function reviewMove(params: {
  fenBefore: string;
  fenAfter: string;
  moveUci: string;
  elo: number;
  moveHistoryPgn?: string;
  selectedPlanId?: string | null;
  moveHistoryUci?: string[];
}): Promise<ReviewMoveResponse> {
  return requestJson<ReviewMoveResponse>("/review-move", params);
}

export function requestBotMove(params: {
  fen: string;
  elo: number;
  skillLevel?: SkillLevel;
  maxMoves: number;
  engineDepth?: number;
  botStyle?: "balanced" | "safe" | "aggressive" | "solid" | "educational";
  selectedBotPlanId?: string | null;
  userPlanId?: string | null;
  strategyState?: Record<string, unknown>;
}): Promise<BotMoveResponse> {
  return requestJson<BotMoveResponse>("/bot-move", {
    ...params,
    botStyle: params.botStyle ?? "balanced"
  });
}

export function getPositionPlan(fen: string, moveHistoryUci: string[]): Promise<PositionPlanResponse> {
  return requestJson<PositionPlanResponse>("/position-plan", {
    fen,
    moveHistoryUci
  });
}

export function listAvailablePlans(side?: string, elo?: number, firstMove?: string): Promise<{ plans: StrategyPlan[] }> {
  const params = new URLSearchParams();
  if (side) params.set("side", side);
  if (elo) params.set("elo", String(elo));
  if (firstMove) params.set("firstMove", firstMove);
  const query = params.toString();
  return getJson<{ plans: StrategyPlan[] }>(`/available-plans${query ? `?${query}` : ""}`);
}

export function getPlanRecommendations(params: {
  fen: string;
  selectedPlanId?: string | null;
  elo: number;
  skillLevel?: SkillLevel;
  moveHistoryUci: string[];
  maxMoves: number;
  engineDepth?: number;
}): Promise<PlanRecommendationsResponse> {
  return requestJson<PlanRecommendationsResponse>("/plan-recommendations", {
    ...params,
    engineDepth: params.engineDepth ?? 10
  });
}
