"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Chess, Move, Square } from "chess.js";
import { ChessCoachBoard } from "@/components/ChessCoachBoard";
import { GameControls } from "@/components/GameControls";
import { GlossaryPanel } from "@/components/GlossaryPanel";
import { LastMoveReviewPanel } from "@/components/LastMoveReviewPanel";
import { MoveExplanationPanel } from "@/components/MoveExplanationPanel";
import { MoveHistory } from "@/components/MoveHistory";
import { OpeningMiniBoard } from "@/components/OpeningMiniBoard";
import { OpeningRepertoirePanel } from "@/components/OpeningRepertoirePanel";
import { PlanFirstPanel } from "@/components/PlanFirstPanel";
import { SkillLevelSelector } from "@/components/SkillLevelSelector";
import { explainMove, getPlanRecommendations, listAvailablePlans, requestBotMove, reviewMove } from "@/lib/api";
import { canMoveInMode, gameStatus, isPromotionAttempt, tryMove } from "@/lib/chess";
import { skillSettings } from "@/lib/skillLevel";
import type {
  CandidateMove,
  ExplainResponse,
  Orientation,
  PlanRecommendation,
  PlanRecommendationsResponse,
  PlayMode,
  ReviewMoveResponse,
  SkillLevel,
  StrategyPlan
} from "@/lib/types";

type PendingPromotion = {
  from: string;
  to: string;
};

type VerboseMove = Move & {
  before?: string;
  after?: string;
};

type LastMoveForReview = {
  fenBefore: string;
  fenAfter: string;
  moveUci: string;
  ply: number;
  source: "manual" | "bot";
};

type SideFilter = "all" | "white" | "black";

export default function HomePage() {
  const [game, setGame] = useState(() => new Chess());
  const [hasStartedPlan, setHasStartedPlan] = useState(false);
  const [orientation, setOrientation] = useState<Orientation>("white");
  const [mode, setMode] = useState<PlayMode>("both");
  const [skillLevel, setSkillLevel] = useState<SkillLevel>("beginner");
  const [sideFilter, setSideFilter] = useState<SideFilter>("all");
  const [boardWidth, setBoardWidth] = useState(360);
  const [selectedSquare, setSelectedSquare] = useState<string | null>(null);
  const [pendingPromotion, setPendingPromotion] = useState<PendingPromotion | null>(null);
  const [lastMessage, setLastMessage] = useState<string | null>(null);
  const [plans, setPlans] = useState<StrategyPlan[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [planRecommendations, setPlanRecommendations] = useState<PlanRecommendationsResponse | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const [selectedMove, setSelectedMove] = useState<CandidateMove | null>(null);
  const [explanation, setExplanation] = useState<ExplainResponse | null>(null);
  const [explanationLoading, setExplanationLoading] = useState(false);
  const [explanationError, setExplanationError] = useState<string | null>(null);
  const [lastReview, setLastReview] = useState<ReviewMoveResponse | null>(null);
  const [reviewsByPly, setReviewsByPly] = useState<Record<number, ReviewMoveResponse>>({});
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [lastMoveForReview, setLastMoveForReview] = useState<LastMoveForReview | null>(null);
  const [botThinking, setBotThinking] = useState(false);
  const [botError, setBotError] = useState<string | null>(null);
  const [highlightedMove, setHighlightedMove] = useState<{ from: string; to: string } | null>(null);
  const [botStrategyState, setBotStrategyState] = useState<Record<string, unknown>>({});

  const settings = useMemo(() => skillSettings(skillLevel), [skillLevel]);
  const elo = settings.elo;
  const fen = game.fen();
  const history = useMemo(() => game.history({ verbose: true }) as VerboseMove[], [game]);
  const status = useMemo(() => gameStatus(game), [game]);
  const pgn = useMemo(() => game.pgn(), [game]);
  const historyUci = useMemo(() => history.map((move) => `${move.from}${move.to}${move.promotion ?? ""}`), [history]);
  const selectedPlan = useMemo(() => plans.find((plan) => plan.id === selectedPlanId) ?? null, [plans, selectedPlanId]);
  const filteredPlans = useMemo(
    () => plans.filter((plan) => sideFilter === "all" || plan.side === sideFilter || plan.side === "universal"),
    [plans, sideFilter]
  );

  useEffect(() => {
    function updateBoardWidth() {
      const width = Math.min(window.innerWidth * 0.92, 560);
      setBoardWidth(Math.floor(width));
    }
    updateBoardWidth();
    window.addEventListener("resize", updateBoardWidth);
    return () => window.removeEventListener("resize", updateBoardWidth);
  }, []);

  useEffect(() => {
    let active = true;
    listAvailablePlans(undefined, elo)
      .then((response) => {
        if (!active) return;
        setPlans(response.plans);
        setSelectedPlanId((current) => current ?? response.plans[0]?.id ?? null);
      })
      .catch(() => {
        if (active) setPlans([]);
      });
    return () => {
      active = false;
    };
  }, [elo]);

  useEffect(() => {
    if (!hasStartedPlan || !selectedPlanId) {
      setPlanRecommendations(null);
      return;
    }
    let active = true;
    setPlanLoading(true);
    setPlanError(null);
    getPlanRecommendations({
      fen,
      selectedPlanId,
      elo,
      skillLevel,
      moveHistoryUci: historyUci,
      maxMoves: settings.maxMoves,
      engineDepth: settings.engineDepth
    })
      .then((response) => {
        if (active) setPlanRecommendations(response);
      })
      .catch((error: Error) => {
        if (!active) return;
        setPlanRecommendations(null);
        setPlanError(error.message || "Impossible de mettre à jour le plan.");
      })
      .finally(() => {
        if (active) setPlanLoading(false);
      });
    return () => {
      active = false;
    };
  }, [elo, fen, hasStartedPlan, historyUci, selectedPlanId, settings.engineDepth, settings.maxMoves, skillLevel]);

  const legalTargets = useMemo(() => {
    if (!selectedSquare) return [];
    return game.moves({ square: selectedSquare as Square, verbose: true }).map((move) => move.to);
  }, [game, selectedSquare]);

  const rememberMoveForReview = useCallback((fenBefore: string, fenAfter: string, moveUci: string, ply: number, source: "manual" | "bot") => {
    setLastMoveForReview({ fenBefore, fenAfter, moveUci, ply, source });
    setLastReview(null);
    setReviewError(null);
  }, []);

  const applyMove = useCallback(
    (from: string, to: string, promotion?: string, source: "manual" | "bot" = "manual") => {
      if (source === "manual" && !canMoveInMode(game, mode)) {
        setLastMessage("Ce mode ne permet pas de jouer ce camp.");
        return false;
      }

      const fenBefore = game.fen();
      const result = tryMove(game, from, to, promotion);
      if (!result) {
        setLastMessage("Coup illégal refusé.");
        return false;
      }

      const moveUci = `${from}${to}${promotion ?? ""}`;
      const ply = history.length + 1;
      setGame(result.game);
      setSelectedSquare(null);
      setPendingPromotion(null);
      setLastMessage(null);
      setBotError(null);
      rememberMoveForReview(fenBefore, result.game.fen(), moveUci, ply, source);
      return true;
    },
    [game, history.length, mode, rememberMoveForReview]
  );

  const requestMove = useCallback(
    (from: string, to: string) => {
      if (isPromotionAttempt(game, from, to)) {
        setPendingPromotion({ from, to });
        return false;
      }
      return applyMove(from, to);
    },
    [applyMove, game]
  );

  useEffect(() => {
    if (!hasStartedPlan || (mode !== "white" && mode !== "black")) {
      return;
    }
    if (game.isGameOver() || pendingPromotion || botThinking || botError) {
      return;
    }

    const userTurn = mode === "white" ? game.turn() === "w" : game.turn() === "b";
    if (userTurn) {
      return;
    }

    let cancelled = false;
    const fenBefore = game.fen();
    const ply = history.length + 1;
    setBotThinking(true);
    setBotError(null);

    requestBotMove({
      fen: fenBefore,
      elo,
      skillLevel,
      maxMoves: settings.maxMoves,
      engineDepth: settings.engineDepth,
      botStyle: "educational",
      selectedBotPlanId: selectedPlanId,
      userPlanId: selectedPlanId,
      strategyState: { ...botStrategyState, moveHistoryUci: historyUci }
    })
      .then(async (response) => {
        await new Promise((resolve) => setTimeout(resolve, 600));
        if (cancelled) return;
        const from = response.move.moveUci.slice(0, 2);
        const to = response.move.moveUci.slice(2, 4);
        const promotion = response.move.moveUci.slice(4) || undefined;
        const botGame = new Chess(fenBefore);
        const result = tryMove(botGame, from, to, promotion);
        if (!result) {
          setBotError("Le bot a proposé un coup illégal, il a été refusé.");
          return;
        }
        setBotStrategyState(response.updatedStrategyState);
        setGame(result.game);
        setHighlightedMove({ from, to });
        rememberMoveForReview(fenBefore, result.game.fen(), response.move.moveUci, ply, "bot");
      })
      .catch((error: Error) => setBotError(error.message || "Le bot n'a pas pu jouer."))
      .finally(() => {
        if (!cancelled) setBotThinking(false);
      });

    return () => {
      cancelled = true;
    };
  }, [botError, botStrategyState, botThinking, elo, game, hasStartedPlan, history.length, historyUci, mode, pendingPromotion, rememberMoveForReview, selectedPlanId, settings.engineDepth, settings.maxMoves, skillLevel]);

  const handleSquareClick = useCallback(
    (square: string) => {
      const piece = game.get(square as Square);
      if (!selectedSquare) {
        if (piece && piece.color === game.turn() && canMoveInMode(game, mode)) {
          setSelectedSquare(square);
        }
        return;
      }

      if (selectedSquare === square) {
        setSelectedSquare(null);
        return;
      }

      if (piece && piece.color === game.turn()) {
        setSelectedSquare(square);
        return;
      }

      requestMove(selectedSquare, square);
    },
    [game, mode, requestMove, selectedSquare]
  );

  const handlePlanSelect = useCallback(
    (planId: string) => {
      const plan = plans.find((item) => item.id === planId);
      setSelectedPlanId(planId);
      setHasStartedPlan(true);
      setGame(new Chess());
      setReviewsByPly({});
      setLastReview(null);
      setLastMoveForReview(null);
      setExplanation(null);
      setSelectedMove(null);
      setHighlightedMove(null);
      setLastMessage(null);
      if (plan?.side === "black") {
        setOrientation("black");
      } else if (plan?.side === "white") {
        setOrientation("white");
      }
    },
    [plans]
  );

  const handlePlanRecommendationSelect = useCallback(
    (recommendation: PlanRecommendation) => {
      setHighlightedMove({ from: recommendation.moveUci.slice(0, 2), to: recommendation.moveUci.slice(2, 4) });
      if (!recommendation.candidate) {
        setLastMessage("Ce coup suit le plan, mais il n'a pas assez de données moteur pour une explication détaillée.");
        return;
      }
      setSelectedMove(recommendation.candidate);
      setExplanation(null);
      setExplanationError(null);
      setExplanationLoading(true);
      explainMove({
        fen,
        elo,
        selectedMove: recommendation.candidate,
        allCandidates: planRecommendations?.technicalEngineMoves ?? [],
        moveHistoryPgn: pgn,
        beginnerMode: true
      })
        .then(setExplanation)
        .catch((error: Error) => setExplanationError(error.message || "Impossible de générer l'explication."))
        .finally(() => setExplanationLoading(false));
    },
    [elo, fen, pgn, planRecommendations?.technicalEngineMoves]
  );

  const reviewStoredMove = useCallback(
    (move: LastMoveForReview) => {
      setReviewLoading(true);
      setReviewError(null);
      reviewMove({ fenBefore: move.fenBefore, fenAfter: move.fenAfter, moveUci: move.moveUci, elo, moveHistoryPgn: pgn })
        .then((review) => {
          setLastReview(review);
          setReviewsByPly((current) => ({ ...current, [move.ply]: review }));
        })
        .catch((error: Error) => setReviewError(error.message || "Impossible d'analyser ce coup."))
        .finally(() => setReviewLoading(false));
    },
    [elo, pgn]
  );

  function undo() {
    const next = new Chess(game.fen());
    next.undo();
    setGame(next);
    setSelectedSquare(null);
    setHighlightedMove(null);
    setLastMessage(null);
    setLastMoveForReview(null);
  }

  function reset() {
    setGame(new Chess());
    setSelectedSquare(null);
    setPendingPromotion(null);
    setHighlightedMove(null);
    setReviewsByPly({});
    setLastReview(null);
    setLastMoveForReview(null);
    setLastMessage(null);
    setExplanation(null);
    setSelectedMove(null);
  }

  function changePlan() {
    reset();
    setHasStartedPlan(false);
  }

  async function copyText(value: string, label: string) {
    await navigator.clipboard.writeText(value);
    setLastMessage(`${label} copié.`);
  }

  function handleHistoryClick(ply: number, move: Move) {
    const review = reviewsByPly[ply];
    setHighlightedMove({ from: move.from, to: move.to });
    if (review) {
      setLastReview(review);
      return;
    }
    const verbose = move as VerboseMove;
    if (verbose.before && verbose.after) {
      reviewStoredMove({
        fenBefore: verbose.before,
        fenAfter: verbose.after,
        moveUci: `${move.from}${move.to}${move.promotion ?? ""}`,
        ply,
        source: "manual"
      });
    }
  }

  if (!hasStartedPlan) {
    return (
      <main className="mx-auto grid min-h-screen w-full max-w-7xl gap-5 px-4 py-4 md:px-6 lg:grid-cols-[minmax(0,1fr)_380px] lg:py-6">
        <section className="grid content-start gap-5">
          <header className="grid gap-2">
            <p className="text-sm font-semibold uppercase text-clay">Chess Elo Coach</p>
            <h1 className="max-w-3xl text-3xl font-bold text-ink sm:text-5xl">Choisis une ouverture, puis suis le plan.</h1>
            <p className="max-w-2xl text-sm leading-6 text-neutral-700">
              Le coach garde ton plan à chaque coup : il vérifie les risques avec Stockfish, puis adapte le prochain objectif si l&apos;adversaire dévie.
            </p>
          </header>

          <section className="panel">
            <SkillLevelSelector value={skillLevel} onChange={setSkillLevel} />
            <div className="mt-4 flex flex-wrap gap-2">
              {(["all", "white", "black"] as SideFilter[]).map((side) => (
                <button
                  key={side}
                  type="button"
                  onClick={() => setSideFilter(side)}
                  className={sideFilter === side ? "rounded bg-night px-3 py-2 text-sm font-semibold text-white" : "rounded border border-line bg-white px-3 py-2 text-sm font-semibold text-night"}
                >
                  {side === "all" ? "Tous" : side === "white" ? "Blancs" : "Noirs"}
                </button>
              ))}
            </div>
          </section>

          <OpeningRepertoirePanel plans={filteredPlans} selectedPlanId={selectedPlanId} onSelect={handlePlanSelect} />
        </section>

        <aside className="grid content-start gap-4">
          <section className="panel">
            <p className="text-xs font-semibold uppercase text-clay">Aperçu</p>
            <h2 className="mt-1 text-xl font-semibold text-night">{selectedPlan?.nameFr ?? "Plan guidé"}</h2>
            <p className="mt-2 text-sm leading-6 text-neutral-700">{selectedPlan?.shortHistory ?? "Sélectionne une carte pour lancer le coach."}</p>
            <div className="mt-4 max-w-64">
              <OpeningMiniBoard fen={selectedPlan?.miniBoardFen} />
            </div>
          </section>
        </aside>
      </main>
    );
  }

  return (
    <main className="mx-auto grid min-h-screen w-full max-w-7xl gap-5 px-4 py-4 md:px-6 lg:grid-cols-[minmax(0,600px)_minmax(0,1fr)] lg:py-6">
      <section className="grid content-start gap-4">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-sm font-semibold uppercase text-clay">{settings.label}</p>
            <h1 className="text-3xl font-bold text-ink sm:text-4xl">Chess Elo Coach</h1>
          </div>
          <div className="rounded border border-line bg-white px-3 py-2 text-sm font-semibold text-night shadow-sm">{status}</div>
        </header>

        <ChessCoachBoard
          fen={fen}
          boardWidth={boardWidth}
          orientation={orientation}
          selectedSquare={selectedSquare}
          legalTargets={legalTargets}
          highlightedMove={highlightedMove}
          onDrop={requestMove}
          onSquareClick={handleSquareClick}
        />

        {botThinking ? <div className="rounded border border-line bg-white px-3 py-2 text-sm text-night">Le bot réfléchit...</div> : null}
        {botError ? <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{botError}</div> : null}

        {pendingPromotion ? (
          <div className="panel">
            <h2 className="panel-title">Promotion</h2>
            <div className="grid grid-cols-4 gap-2">
              {[
                ["q", "Dame"],
                ["r", "Tour"],
                ["b", "Fou"],
                ["n", "Cavalier"]
              ].map(([piece, label]) => (
                <button
                  key={piece}
                  type="button"
                  onClick={() => applyMove(pendingPromotion.from, pendingPromotion.to, piece)}
                  className="rounded border border-line bg-white px-3 py-2 text-sm font-semibold hover:border-clay"
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {mode === "friend" ? (
          <div className="rounded border border-sage bg-white px-3 py-2 text-sm text-night">
            Mode entraînement : reproduis les coups pour comprendre les idées. Aucune partie externe n&apos;est lue automatiquement.
          </div>
        ) : null}
        {lastMessage ? <div className="rounded border border-line bg-white px-3 py-2 text-sm text-night">{lastMessage}</div> : null}

        <section className="panel">
          <SkillLevelSelector value={skillLevel} onChange={setSkillLevel} />
          <div className="mt-4">
            <GameControls
              orientation={orientation}
              onOrientationChange={setOrientation}
              mode={mode}
              onModeChange={setMode}
              onUndo={undo}
              onReset={reset}
              onCopyFen={() => copyText(fen, "FEN")}
              onCopyPgn={() => copyText(pgn || "*", "PGN")}
            />
          </div>
        </section>
      </section>

      <section className="grid content-start gap-4">
        <div className="flex justify-end">
          <button type="button" onClick={changePlan} className="rounded border border-line bg-white px-3 py-2 text-sm font-semibold text-night">
            Changer de plan
          </button>
        </div>

        <PlanFirstPanel
          selectedPlan={selectedPlan}
          recommendations={planRecommendations}
          skillLevel={skillLevel}
          loading={planLoading}
          error={planError}
          onSelectRecommendation={handlePlanRecommendationSelect}
          onReviewLastMove={lastMoveForReview ? () => reviewStoredMove(lastMoveForReview) : undefined}
          canReviewLastMove={Boolean(lastMoveForReview)}
          reviewLoading={reviewLoading}
        />

        <MoveExplanationPanel explanation={explanation} loading={explanationLoading} error={explanationError} />

        {selectedMove ? (
          <div className="rounded border border-line bg-white px-3 py-2 text-xs text-neutral-600">
            Coup sélectionné : {selectedMove.moveSan} / {selectedMove.moveUci}
          </div>
        ) : null}

        {lastReview || reviewLoading || reviewError ? (
          <LastMoveReviewPanel review={lastReview} loading={reviewLoading} error={reviewError} />
        ) : null}

        <details className="panel">
          <summary className="cursor-pointer panel-title">Historique et détails techniques</summary>
          <div className="mt-4 grid gap-4">
            <MoveHistory moves={history} reviews={reviewsByPly} onMoveClick={handleHistoryClick} />
            <div className="grid gap-2 text-sm text-neutral-700">
              <p>FEN : {fen}</p>
              <p>PGN : {pgn || "*"}</p>
              <p>Coups UCI : {historyUci.join(" ") || "aucun"}</p>
            </div>
          </div>
        </details>

        <details className="panel">
          <summary className="cursor-pointer panel-title">Glossaire</summary>
          <div className="mt-4">
            <GlossaryPanel />
          </div>
        </details>
      </section>
    </main>
  );
}
