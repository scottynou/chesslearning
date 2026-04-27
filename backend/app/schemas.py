from __future__ import annotations

from typing import Any, Literal

import chess
from pydantic import BaseModel, ConfigDict, Field, field_validator


Difficulty = Literal["easy", "medium", "hard"]
Risk = Literal["low", "medium", "high"]
SideToMove = Literal["white", "black"]
Quality = Literal["excellent", "good", "playable", "inaccurate", "mistake", "blunder"]
BotStyle = Literal["balanced", "safe", "aggressive", "solid", "educational"]
SkillLevel = Literal["beginner", "intermediate", "pro"]
PlanPhase = Literal["opening", "transition", "middlegame", "endgame"]
PlanStatus = Literal["on_plan", "transposed", "opponent_deviated", "out_of_book", "plan_completed"]


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    fen: str
    elo: int = Field(default=1200, ge=600, le=3200)
    max_moves: int = Field(default=10, alias="maxMoves", ge=1)
    engine_depth: int = Field(default=14, alias="engineDepth", ge=1, le=30)

    @field_validator("fen")
    @classmethod
    def validate_fen(cls, value: str) -> str:
        try:
            chess.Board(value)
        except ValueError as exc:
            raise ValueError("Invalid FEN") from exc
        return value

    @field_validator("max_moves", mode="before")
    @classmethod
    def clamp_max_moves(cls, value: int | str | None) -> int:
        if value is None:
            return 10
        parsed = int(value)
        return max(1, min(10, parsed))


class CandidateMove(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rank: int
    move_uci: str = Field(alias="moveUci")
    move_san: str = Field(alias="moveSan")
    stockfish_rank: int = Field(alias="stockfishRank")
    eval_cp: int | None = Field(default=None, alias="evalCp")
    mate_in: int | None = Field(default=None, alias="mateIn")
    pv: list[str]
    coach_score: int = Field(alias="coachScore")
    engine_score: int = Field(alias="engineScore")
    human_likelihood: int = Field(alias="humanLikelihood")
    simplicity_score: int = Field(alias="simplicityScore")
    risk_penalty: int = Field(alias="riskPenalty")
    difficulty: Difficulty
    risk: Risk
    summary: str


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    fen: str
    elo: int
    side_to_move: SideToMove = Field(alias="sideToMove")
    candidates: list[CandidateMove]


class ExplainRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    fen: str
    elo: int = Field(default=1200, ge=600, le=3200)
    selected_move: CandidateMove = Field(alias="selectedMove")
    all_candidates: list[CandidateMove] = Field(default_factory=list, alias="allCandidates")
    move_history_pgn: str | None = Field(default=None, alias="moveHistoryPgn")

    @field_validator("fen")
    @classmethod
    def validate_fen(cls, value: str) -> str:
        try:
            chess.Board(value)
        except ValueError as exc:
            raise ValueError("Invalid FEN") from exc
        return value


class ExplanationBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    main_idea: str = Field(alias="mainIdea")
    why_for_this_elo: str = Field(alias="whyForThisElo")
    expected_opponent_reaction: str = Field(alias="expectedOpponentReaction")
    plan_a: str = Field(alias="planA")
    plan_b: str = Field(alias="planB")
    what_to_watch: str = Field(alias="whatToWatch")
    common_mistake: str = Field(alias="commonMistake")
    comparison: str


class ExplainResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    move_san: str = Field(alias="moveSan")
    title: str
    explanation: ExplanationBody


class BeginnerMove(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    beginner_label: str = Field(alias="beginnerLabel")
    short_label: str = Field(alias="shortLabel")
    san: str
    french_san: str = Field(alias="frenchSan")
    uci: str
    piece_name: str = Field(alias="pieceName")
    from_square: str = Field(alias="from")
    to_square: str = Field(alias="to")
    icon: str


class TranslatedPvMove(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    move_number: int = Field(alias="moveNumber")
    side: SideToMove
    beginner_label: str = Field(alias="beginnerLabel")
    simple_explanation: str = Field(alias="simpleExplanation")


class ExplainCandidateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    fen: str
    elo: int = Field(default=1200, ge=600, le=3200)
    selected_move: CandidateMove = Field(alias="selectedMove")
    all_candidates: list[CandidateMove] = Field(default_factory=list, alias="allCandidates")
    move_history_pgn: str | None = Field(default=None, alias="moveHistoryPgn")
    beginner_mode: bool = Field(default=True, alias="beginnerMode")

    @field_validator("fen")
    @classmethod
    def validate_fen(cls, value: str) -> str:
        try:
            chess.Board(value)
        except ValueError as exc:
            raise ValueError("Invalid FEN") from exc
        return value


class ExplainCandidateSections(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    what_to_do: str = Field(alias="whatToDo")
    main_idea: str = Field(alias="mainIdea")
    why_now: str = Field(alias="whyNow")
    what_it_provokes: str = Field(alias="whatItProvokes")
    next_plan: list[str] = Field(alias="nextPlan")
    danger: str
    common_mistake: str = Field(alias="commonMistake")
    better_than: str = Field(alias="betterThan")


class ExplainCandidateTechnical(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    san: str
    uci: str
    eval_cp: int | None = Field(default=None, alias="evalCp")
    pv: list[str]


class ExplainCandidateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    move_label: str = Field(alias="moveLabel")
    one_sentence: str = Field(alias="oneSentence")
    sections: ExplainCandidateSections
    technical: ExplainCandidateTechnical
    translated_pv: list[TranslatedPvMove] = Field(default_factory=list, alias="translatedPv")


class ReviewMoveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    fen_before: str = Field(alias="fenBefore")
    fen_after: str = Field(alias="fenAfter")
    move_uci: str = Field(alias="moveUci")
    elo: int = Field(default=1200, ge=600, le=3200)
    move_history_pgn: str | None = Field(default=None, alias="moveHistoryPgn")

    @field_validator("fen_before", "fen_after")
    @classmethod
    def validate_fen(cls, value: str) -> str:
        try:
            chess.Board(value)
        except ValueError as exc:
            raise ValueError("Invalid FEN") from exc
        return value


class ReviewExplanation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    probable_idea: str = Field(alias="probableIdea")
    what_it_does: str = Field(alias="whatItDoes")
    what_it_allows: str = Field(alias="whatItAllows")
    what_to_watch: str = Field(alias="whatToWatch")
    comparison_with_best: str = Field(alias="comparisonWithBest")


class ReviewMoveResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    move_label: str = Field(alias="moveLabel")
    quality: Quality
    quality_label: str = Field(alias="qualityLabel")
    played_move_eval_label: str = Field(alias="playedMoveEvalLabel")
    best_move_label: str = Field(alias="bestMoveLabel")
    best_move_was_different: bool = Field(alias="bestMoveWasDifferent")
    explanation: ReviewExplanation
    connection_to_plan: str | None = Field(default=None, alias="connectionToPlan")
    what_it_attacks: list[str] = Field(default_factory=list, alias="whatItAttacks")
    what_it_defends: list[str] = Field(default_factory=list, alias="whatItDefends")
    what_it_allows_next: list[str] = Field(default_factory=list, alias="whatItAllowsNext")
    best_alternative: dict[str, Any] | None = Field(default=None, alias="bestAlternative")
    warning: str | None = None


class BotMoveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    fen: str
    bot_side: SideToMove | None = Field(default=None, alias="botSide")
    elo: int = Field(default=1200, ge=600, le=3200)
    skill_level: SkillLevel | None = Field(default=None, alias="skillLevel")
    max_moves: int = Field(default=10, alias="maxMoves", ge=1)
    engine_depth: int = Field(default=10, alias="engineDepth", ge=1, le=24)
    selected_bot_plan_id: str | None = Field(default=None, alias="selectedBotPlanId")
    user_plan_id: str | None = Field(default=None, alias="userPlanId")
    strategy_state: dict[str, Any] | None = Field(default=None, alias="strategyState")
    opening_preference: str | None = Field(default=None, alias="openingPreference")
    bot_style: BotStyle = Field(default="balanced", alias="botStyle")

    @field_validator("fen")
    @classmethod
    def validate_fen(cls, value: str) -> str:
        try:
            chess.Board(value)
        except ValueError as exc:
            raise ValueError("Invalid FEN") from exc
        return value

    @field_validator("max_moves", mode="before")
    @classmethod
    def clamp_max_moves(cls, value: int | str | None) -> int:
        if value is None:
            return 10
        parsed = int(value)
        return max(1, min(10, parsed))


class BotMoveResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    move: CandidateMove
    selection_reason: str = Field(alias="selectionReason")
    updated_strategy_state: dict[str, Any] = Field(default_factory=dict, alias="updatedStrategyState")
    explanation_preview: str = Field(alias="explanationPreview")


class PositionPlanRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    fen: str
    move_history_uci: list[str] = Field(default_factory=list, alias="moveHistoryUci")

    @field_validator("fen")
    @classmethod
    def validate_fen(cls, value: str) -> str:
        try:
            chess.Board(value)
        except ValueError as exc:
            raise ValueError("Invalid FEN") from exc
        return value


class PositionPlanResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    phase: Literal["opening", "middlegame", "endgame"]
    phase_label: str = Field(alias="phaseLabel")
    detected_opening: dict[str, Any] | None = Field(default=None, alias="detectedOpening")
    plan: list[str]
    next_objective: str = Field(alias="nextObjective")
    position_context: dict[str, Any] = Field(alias="positionContext")


class AvailablePlansResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    plans: list[dict[str, Any]]


class PlanRecommendationsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    fen: str
    selected_plan_id: str | None = Field(default=None, alias="selectedPlanId")
    elo: int = Field(default=1200, ge=600, le=3200)
    skill_level: SkillLevel | None = Field(default=None, alias="skillLevel")
    move_history_uci: list[str] = Field(default_factory=list, alias="moveHistoryUci")
    max_moves: int = Field(default=10, alias="maxMoves", ge=1)
    engine_depth: int = Field(default=10, alias="engineDepth", ge=1, le=24)

    @field_validator("fen")
    @classmethod
    def validate_fen(cls, value: str) -> str:
        try:
            chess.Board(value)
        except ValueError as exc:
            raise ValueError("Invalid FEN") from exc
        return value

    @field_validator("max_moves", mode="before")
    @classmethod
    def clamp_max_moves(cls, value: int | str | None) -> int:
        if value is None:
            return 10
        parsed = int(value)
        return max(1, min(10, parsed))


class GamePlanState(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    selected_plan_id: str | None = Field(default=None, alias="selectedPlanId")
    plan_name: str | None = Field(default=None, alias="planName")
    side: str | None = None
    phase: PlanPhase
    status: PlanStatus
    current_step_index: int = Field(alias="currentStepIndex")
    current_goals: list[str] = Field(alias="currentGoals")
    next_objectives: list[str] = Field(alias="nextObjectives")
    known_opponent_deviation: dict[str, Any] | None = Field(default=None, alias="knownOpponentDeviation")
    recommended_plan_moves: list[str] = Field(default_factory=list, alias="recommendedPlanMoves")
    fallback_principles: list[str] = Field(default_factory=list, alias="fallbackPrinciples")
    engine_safety_warning: str | None = Field(default=None, alias="engineSafetyWarning")
    status_explanation: str = Field(alias="statusExplanation")


class PlanRecommendationsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    plan_state: GamePlanState = Field(alias="planState")
    plan_moves: list[dict[str, Any]] = Field(alias="planMoves")
    engine_moves: list[CandidateMove] = Field(alias="engineMoves")
    merged_recommendations: list[dict[str, Any]] = Field(alias="mergedRecommendations")
    explanation_context: dict[str, Any] = Field(alias="explanationContext")
    selected_plan: dict[str, Any] | None = Field(default=None, alias="selectedPlan")
    phase: PlanPhase = "opening"
    phase_status: str = Field(default="opening_in_progress", alias="phaseStatus")
    plan_progress: dict[str, Any] = Field(default_factory=dict, alias="planProgress")
    current_objective: str = Field(default="", alias="currentObjective")
    last_event: str = Field(default="", alias="lastEvent")
    what_changed: str = Field(default="", alias="whatChanged")
    next_objective: str = Field(default="", alias="nextObjective")
    recommended_plan_moves: list[dict[str, Any]] = Field(default_factory=list, alias="recommendedPlanMoves")
    primary_move: dict[str, Any] | None = Field(default=None, alias="primaryMove")
    adapted_alternatives: list[dict[str, Any]] = Field(default_factory=list, alias="adaptedAlternatives")
    blocked_expected_move: dict[str, Any] | None = Field(default=None, alias="blockedExpectedMove")
    coach_message: str = Field(default="", alias="coachMessage")
    pedagogical_summary: str = Field(default="", alias="pedagogicalSummary")
    move_complexity: str = Field(default="simple", alias="moveComplexity")
    technical_details: dict[str, Any] = Field(default_factory=dict, alias="technicalDetails")
    technical_engine_moves: list[CandidateMove] = Field(default_factory=list, alias="technicalEngineMoves")
