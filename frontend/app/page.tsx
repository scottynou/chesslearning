"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Chess, Move, Square } from "chess.js";
import { ChessCoachBoard } from "@/components/ChessCoachBoard";
import { GameControls } from "@/components/GameControls";
import { GlossaryPanel } from "@/components/GlossaryPanel";
import { LastMoveReviewPanel } from "@/components/LastMoveReviewPanel";
import { MoveHistory } from "@/components/MoveHistory";
import { OpeningRepertoirePanel } from "@/components/OpeningRepertoirePanel";
import { PlanFirstPanel } from "@/components/PlanFirstPanel";
import { SideSelectionPanel } from "@/components/SideSelectionPanel";
import { getPlanRecommendations, listAvailablePlans, requestBotMove, reviewMove } from "@/lib/api";
import { canMoveInMode, gameStatus, isPromotionAttempt, tryMove } from "@/lib/chess";
import type {
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

type AppStage = "side-selection" | "white-plan-selection" | "black-first-move" | "black-plan-selection" | "coach";
type UserSide = "white" | "black" | "both";

const INTERNAL_SKILL_LEVEL: SkillLevel = "beginner";
const INTERNAL_ELO = 1200;
const INTERNAL_MAX_MOVES = 5;
const INTERNAL_ENGINE_DEPTH = 8;

export default function HomePage() {
  const [game, setGame] = useState(() => new Chess());
  const [appStage, setAppStage] = useState<AppStage>("side-selection");
  const [userSide, setUserSide] = useState<UserSide>("white");
  const [orientation, setOrientation] = useState<Orientation>("white");
  const [mode, setMode] = useState<PlayMode>("both");
  const [boardWidth, setBoardWidth] = useState(360);
  const [selectedSquare, setSelectedSquare] = useState<string | null>(null);
  const [pendingPromotion, setPendingPromotion] = useState<PendingPromotion | null>(null);
  const [lastMessage, setLastMessage] = useState<string | null>(null);
  const [plans, setPlans] = useState<StrategyPlan[]>([]);
  const [plansLoading, setPlansLoading] = useState(false);
  const [plansError, setPlansError] = useState<string | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [firstOpponentMove, setFirstOpponentMove] = useState<string | null>(null);
  const [planRecommendations, setPlanRecommendations] = useState<PlanRecommendationsResponse | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const [lastReview, setLastReview] = useState<ReviewMoveResponse | null>(null);
  const [reviewsByPly, setReviewsByPly] = useState<Record<number, ReviewMoveResponse>>({});
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [lastMoveForReview, setLastMoveForReview] = useState<LastMoveForReview | null>(null);
  const [botThinking, setBotThinking] = useState(false);
  const [botError, setBotError] = useState<string | null>(null);
  const [highlightedMove, setHighlightedMove] = useState<{ from: string; to: string } | null>(null);
  const [highlightedRecommendationUci, setHighlightedRecommendationUci] = useState<string | null>(null);
  const [botStrategyState, setBotStrategyState] = useState<Record<string, unknown>>({});
  const [menuOpen, setMenuOpen] = useState(false);

  const fen = game.fen();
  const history = useMemo(() => game.history({ verbose: true }) as VerboseMove[], [game]);
  const status = useMemo(() => gameStatus(game), [game]);
  const pgn = useMemo(() => game.pgn(), [game]);
  const historyUci = useMemo(() => history.map((move) => `${move.from}${move.to}${move.promotion ?? ""}`), [history]);
  const selectedPlan = useMemo(() => {
    return plans.find((plan) => plan.id === selectedPlanId) ?? (planRecommendations?.selectedPlan as StrategyPlan | null) ?? null;
  }, [plans, planRecommendations?.selectedPlan, selectedPlanId]);
  const boardLocked = appStage === "black-plan-selection" || appStage === "white-plan-selection" || appStage === "side-selection";

  useEffect(() => {
    const primaryUci = planRecommendations?.primaryMove?.moveUci;
    if (appStage !== "coach" || !primaryUci) {
      return;
    }
    setHighlightedRecommendationUci(primaryUci);
    setHighlightedMove({ from: primaryUci.slice(0, 2), to: primaryUci.slice(2, 4) });
  }, [appStage, planRecommendations?.primaryMove?.moveUci]);

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
    if (appStage !== "white-plan-selection" && appStage !== "black-plan-selection") {
      return;
    }

    const side = appStage === "white-plan-selection" ? "white" : "black";
    const firstMove = appStage === "black-plan-selection" ? firstOpponentMove ?? undefined : undefined;
    let active = true;
    setPlansLoading(true);
    setPlansError(null);

    listAvailablePlans(side, undefined, firstMove)
      .then((response) => {
        if (!active) return;
        setPlans(response.plans);
      })
      .catch((error: Error) => {
        if (!active) return;
        setPlans([]);
        setPlansError(error.message || "Impossible de charger les plans.");
      })
      .finally(() => {
        if (active) setPlansLoading(false);
      });

    return () => {
      active = false;
    };
  }, [appStage, firstOpponentMove]);

  useEffect(() => {
    if (appStage !== "coach") {
      setPlanRecommendations(null);
      return;
    }
    if (!selectedPlanId && userSide !== "both") {
      setPlanRecommendations(null);
      return;
    }

    let active = true;
    setPlanLoading(true);
    setPlanError(null);
    getPlanRecommendations({
      fen,
      selectedPlanId,
      elo: INTERNAL_ELO,
      skillLevel: INTERNAL_SKILL_LEVEL,
      moveHistoryUci: historyUci,
      maxMoves: INTERNAL_MAX_MOVES,
      engineDepth: INTERNAL_ENGINE_DEPTH
    })
      .then((response) => {
        if (active) setPlanRecommendations(response);
      })
      .catch((error: Error) => {
        if (!active) return;
        setPlanRecommendations(null);
        setPlanError(error.message || "Impossible de mettre a jour le plan.");
      })
      .finally(() => {
        if (active) setPlanLoading(false);
      });

    return () => {
      active = false;
    };
  }, [appStage, fen, historyUci, selectedPlanId, userSide]);

  const legalTargets = useMemo(() => {
    if (!selectedSquare || boardLocked) return [];
    return game.moves({ square: selectedSquare as Square, verbose: true }).map((move) => move.to);
  }, [boardLocked, game, selectedSquare]);

  const rememberMoveForReview = useCallback((fenBefore: string, fenAfter: string, moveUci: string, ply: number, source: "manual" | "bot") => {
    setLastMoveForReview({ fenBefore, fenAfter, moveUci, ply, source });
    setLastReview(null);
    setReviewError(null);
  }, []);

  const applyMove = useCallback(
    (from: string, to: string, promotion?: string, source: "manual" | "bot" = "manual") => {
      if (boardLocked) {
        setLastMessage("Choisis d'abord ton plan avant de continuer la partie.");
        return false;
      }
      if (source === "manual" && !canMoveInMode(game, mode)) {
        setLastMessage("Ce mode ne permet pas de jouer ce camp.");
        return false;
      }

      const fenBefore = game.fen();
      const result = tryMove(game, from, to, promotion);
      if (!result) {
        setLastMessage("Coup illegal refuse.");
        return false;
      }

      const moveUci = `${from}${to}${promotion ?? ""}`;
      const ply = history.length + 1;
      setGame(result.game);
      setSelectedSquare(null);
      setPendingPromotion(null);
      setBotError(null);
      setHighlightedMove({ from, to });
      setHighlightedRecommendationUci(null);
      rememberMoveForReview(fenBefore, result.game.fen(), moveUci, ply, source);

      if (appStage === "black-first-move" && history.length === 0 && source === "manual") {
        setFirstOpponentMove(moveUci);
        setAppStage("black-plan-selection");
        setLastMessage("Premier coup blanc enregistre. Choisis maintenant une reponse noire adaptee.");
      } else {
        setLastMessage(null);
      }
      return true;
    },
    [appStage, boardLocked, game, history.length, mode, rememberMoveForReview]
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
    if (appStage !== "coach" || (mode !== "white" && mode !== "black")) {
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
      elo: INTERNAL_ELO,
      skillLevel: INTERNAL_SKILL_LEVEL,
      maxMoves: INTERNAL_MAX_MOVES,
      engineDepth: INTERNAL_ENGINE_DEPTH,
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
          setBotError("Le bot a propose un coup illegal, il a ete refuse.");
          return;
        }
        setBotStrategyState(response.updatedStrategyState);
        setGame(result.game);
        setHighlightedMove({ from, to });
        setHighlightedRecommendationUci(null);
        rememberMoveForReview(fenBefore, result.game.fen(), response.move.moveUci, ply, "bot");
      })
      .catch((error: Error) => setBotError(error.message || "Le bot n'a pas pu jouer."))
      .finally(() => {
        if (!cancelled) setBotThinking(false);
      });

    return () => {
      cancelled = true;
    };
  }, [appStage, botError, botStrategyState, botThinking, game, history.length, historyUci, mode, pendingPromotion, rememberMoveForReview, selectedPlanId]);

  const handleSquareClick = useCallback(
    (square: string) => {
      if (boardLocked) return;
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
    [boardLocked, game, mode, requestMove, selectedSquare]
  );

  function startWhiteFlow() {
    resetBoardOnly();
    setUserSide("white");
    setOrientation("white");
    setMode("both");
    setSelectedPlanId(null);
    setFirstOpponentMove(null);
    setPlans([]);
    setAppStage("white-plan-selection");
  }

  function startBlackFlow() {
    resetBoardOnly();
    setUserSide("black");
    setOrientation("black");
    setMode("both");
    setSelectedPlanId(null);
    setFirstOpponentMove(null);
    setPlans([]);
    setAppStage("black-first-move");
  }

  function startFreeMode() {
    resetBoardOnly();
    setUserSide("both");
    setOrientation("white");
    setMode("both");
    setSelectedPlanId(null);
    setPlans([]);
    setAppStage("coach");
  }

  const handlePlanSelect = useCallback(
    (planId: string) => {
      const plan = plans.find((item) => item.id === planId);
      setSelectedPlanId(planId);
      setAppStage("coach");
      setReviewsByPly({});
      setLastReview(null);
      setLastMoveForReview(null);
      setPlanRecommendations(null);
      setHighlightedMove(null);
      setHighlightedRecommendationUci(null);
      setLastMessage(null);
      setMenuOpen(false);
      if (plan?.side === "black") {
        setOrientation("black");
      } else if (plan?.side === "white") {
        setOrientation("white");
      }
      if (userSide !== "black") {
        setGame(new Chess());
      }
    },
    [plans, userSide]
  );

  const handlePlanRecommendationToggle = useCallback((recommendation: PlanRecommendation) => {
    if (highlightedRecommendationUci === recommendation.moveUci) {
      setHighlightedRecommendationUci(null);
      setHighlightedMove(null);
      return;
    }
    setHighlightedRecommendationUci(recommendation.moveUci);
    setHighlightedMove({ from: recommendation.moveUci.slice(0, 2), to: recommendation.moveUci.slice(2, 4) });
  }, [highlightedRecommendationUci]);

  const reviewStoredMove = useCallback(
    (move: LastMoveForReview) => {
      setReviewLoading(true);
      setReviewError(null);
      reviewMove({ fenBefore: move.fenBefore, fenAfter: move.fenAfter, moveUci: move.moveUci, elo: INTERNAL_ELO, moveHistoryPgn: pgn })
        .then((review) => {
          setLastReview(review);
          setReviewsByPly((current) => ({ ...current, [move.ply]: review }));
        })
        .catch((error: Error) => setReviewError(error.message || "Impossible d'analyser ce coup."))
        .finally(() => setReviewLoading(false));
    },
    [pgn]
  );

  function resetBoardOnly() {
    setGame(new Chess());
    setSelectedSquare(null);
    setPendingPromotion(null);
    setHighlightedMove(null);
    setHighlightedRecommendationUci(null);
    setReviewsByPly({});
    setLastReview(null);
    setLastMoveForReview(null);
    setLastMessage(null);
    setPlanRecommendations(null);
  }

  function undo() {
    const nextHistory = historyUci.slice(0, -1);
    const next = new Chess();
    for (const move of nextHistory) {
      next.move({
        from: move.slice(0, 2),
        to: move.slice(2, 4),
        ...(move.slice(4) ? { promotion: move.slice(4) } : {})
      });
    }
    setGame(next);
    setSelectedSquare(null);
    setHighlightedMove(null);
    setHighlightedRecommendationUci(null);
    setLastMessage(null);
    setLastMoveForReview(null);
    if (userSide === "black" && nextHistory.length === 0) {
      setSelectedPlanId(null);
      setFirstOpponentMove(null);
      setPlans([]);
      setAppStage("black-first-move");
    }
  }

  function reset() {
    resetBoardOnly();
    if (userSide === "black") {
      setSelectedPlanId(null);
      setFirstOpponentMove(null);
      setPlans([]);
      setAppStage("black-first-move");
    }
  }

  function changePlan() {
    resetBoardOnly();
    setSelectedPlanId(null);
    setFirstOpponentMove(null);
    setPlans([]);
    setAppStage("side-selection");
    setMenuOpen(false);
  }

  async function copyText(value: string, label: string) {
    await navigator.clipboard.writeText(value);
    setLastMessage(`${label} copie.`);
  }

  function handleHistoryClick(ply: number, move: Move) {
    const review = reviewsByPly[ply];
    setHighlightedMove({ from: move.from, to: move.to });
    setHighlightedRecommendationUci(null);
    if (review) {
      setLastReview(review);
      setMenuOpen(true);
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
      setMenuOpen(true);
    }
  }

  if (appStage === "side-selection") {
    return (
      <main>
        <SideSelectionPanel onChooseWhite={startWhiteFlow} onChooseBlack={startBlackFlow} onChooseFreeMode={startFreeMode} />
      </main>
    );
  }

  if (appStage === "black-first-move") {
    return (
      <main className="mx-auto grid min-h-screen w-full max-w-[1800px] gap-5 px-4 py-4 md:px-6 lg:grid-cols-[minmax(0,600px)_minmax(0,1fr)] lg:py-6">
        <section className="grid content-start gap-4">
          <Header status={status} menuOpen={menuOpen} setMenuOpen={setMenuOpen} changePlan={changePlan} />
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
          {lastMessage ? <div className="rounded border border-line bg-white px-3 py-2 text-sm text-night">{lastMessage}</div> : null}
        </section>
        <section className="panel self-start">
          <p className="text-xs font-semibold uppercase text-clay">Je joue les noirs</p>
          <h1 className="mt-1 text-2xl font-bold text-night">Entre le premier coup blanc</h1>
          <p className="mt-2 text-sm leading-6 text-neutral-700">
            Joue le premier coup des blancs sur l&apos;echiquier. Apres 1.e4, le coach proposera par exemple Caro-Kann, e5 classique, Francaise, Sicilienne ou Scandinave. Apres 1.d4, il proposera des plans dame-pion.
          </p>
        </section>
      </main>
    );
  }

  if (appStage === "white-plan-selection" || appStage === "black-plan-selection") {
    const isBlack = appStage === "black-plan-selection";
    return (
      <main className="mx-auto min-h-screen w-full max-w-[1800px] px-4 py-4 md:px-8 lg:py-8">
        <section className="grid content-start gap-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <button type="button" onClick={changePlan} className="rounded border border-line bg-white px-3 py-2 text-sm font-semibold text-night">
              Retour au choix du camp
            </button>
            {isBlack ? <span className="rounded bg-night px-3 py-2 text-sm font-semibold text-white">Premier coup : {history[0]?.san ?? firstOpponentMove}</span> : null}
          </div>
          {isBlack ? (
            <ChessCoachBoard
              fen={fen}
              boardWidth={Math.min(boardWidth, 360)}
              orientation={orientation}
              selectedSquare={null}
              legalTargets={[]}
              highlightedMove={highlightedMove}
              onDrop={requestMove}
              onSquareClick={handleSquareClick}
            />
          ) : null}
          {plansLoading ? <div className="panel text-sm text-neutral-700">Chargement des plans...</div> : null}
          {plansError ? <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{plansError}</div> : null}
          <OpeningRepertoirePanel
            plans={plans}
            selectedPlanId={selectedPlanId}
            onSelect={handlePlanSelect}
            title={isBlack ? "Choisis ta reponse avec les noirs" : "Choisis ton ouverture avec les blancs"}
            intro={isBlack ? "Ces plans sont filtres selon le premier coup blanc. Le plan choisi restera verrouille, puis le coach adaptera seulement les prochains coups." : "Choisis une ouverture blanche. Ensuite, le coach t'aide a atteindre le milieu de partie avec un plan clair."}
          />
        </section>
      </main>
    );
  }

  return (
    <main className="mx-auto grid min-h-screen w-full max-w-[1800px] gap-5 px-4 py-4 md:px-6 lg:grid-cols-[minmax(0,600px)_minmax(0,1fr)] lg:py-6">
      <section className="grid content-start gap-4">
        <Header status={status} menuOpen={menuOpen} setMenuOpen={setMenuOpen} changePlan={changePlan} />

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

        <div className="grid grid-cols-3 gap-2">
          <button type="button" onClick={undo} className="control-button">Annuler</button>
          <button type="button" onClick={reset} className="control-button">Reset</button>
          <button type="button" onClick={() => setOrientation(orientation === "white" ? "black" : "white")} className="control-button">Tourner</button>
        </div>

        {botThinking ? <div className="rounded border border-line bg-white px-3 py-2 text-sm text-night">Le bot reflechit...</div> : null}
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

        {lastMessage ? <div className="rounded border border-line bg-white px-3 py-2 text-sm text-night">{lastMessage}</div> : null}
      </section>

      <section className="grid content-start gap-4">
        <PlanFirstPanel
          selectedPlan={selectedPlan}
          recommendations={planRecommendations}
          loading={planLoading}
          error={planError}
          highlightedMoveUci={highlightedRecommendationUci}
          onToggleRecommendation={handlePlanRecommendationToggle}
        />

        {menuOpen ? (
          <CoachUtilityMenu
            orientation={orientation}
            setOrientation={setOrientation}
            mode={mode}
            setMode={setMode}
            undo={undo}
            reset={reset}
            copyFen={() => copyText(fen, "FEN")}
            copyPgn={() => copyText(pgn || "*", "PGN")}
            lastMoveForReview={lastMoveForReview}
            reviewStoredMove={reviewStoredMove}
            reviewLoading={reviewLoading}
            reviewError={reviewError}
            lastReview={lastReview}
            history={history}
            reviewsByPly={reviewsByPly}
            handleHistoryClick={handleHistoryClick}
            fen={fen}
            pgn={pgn}
            historyUci={historyUci}
          />
        ) : null}
      </section>
    </main>
  );
}

function Header({
  status,
  menuOpen,
  setMenuOpen,
  changePlan
}: {
  status: string;
  menuOpen: boolean;
  setMenuOpen: (value: boolean) => void;
  changePlan: () => void;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <p className="text-sm font-semibold uppercase text-clay">Chess Learning</p>
        <h1 className="text-3xl font-bold text-ink sm:text-4xl">Coach de plan</h1>
      </div>
      <div className="flex items-center gap-2">
        <span className="rounded border border-line bg-white px-3 py-2 text-sm font-semibold text-night shadow-sm">{status}</span>
        <button type="button" onClick={() => setMenuOpen(!menuOpen)} className="rounded border border-line bg-white px-3 py-2 text-sm font-semibold text-night">
          Menu
        </button>
        <button type="button" onClick={changePlan} className="rounded border border-line bg-white px-3 py-2 text-sm font-semibold text-night">
          Changer de plan
        </button>
      </div>
    </header>
  );
}

function CoachUtilityMenu({
  orientation,
  setOrientation,
  mode,
  setMode,
  undo,
  reset,
  copyFen,
  copyPgn,
  lastMoveForReview,
  reviewStoredMove,
  reviewLoading,
  reviewError,
  lastReview,
  history,
  reviewsByPly,
  handleHistoryClick,
  fen,
  pgn,
  historyUci
}: {
  orientation: Orientation;
  setOrientation: (value: Orientation) => void;
  mode: PlayMode;
  setMode: (value: PlayMode) => void;
  undo: () => void;
  reset: () => void;
  copyFen: () => void;
  copyPgn: () => void;
  lastMoveForReview: LastMoveForReview | null;
  reviewStoredMove: (move: LastMoveForReview) => void;
  reviewLoading: boolean;
  reviewError: string | null;
  lastReview: ReviewMoveResponse | null;
  history: VerboseMove[];
  reviewsByPly: Record<number, ReviewMoveResponse>;
  handleHistoryClick: (ply: number, move: Move) => void;
  fen: string;
  pgn: string;
  historyUci: string[];
}) {
  return (
    <aside className="panel">
      <h2 className="panel-title">Menu</h2>
      <div className="grid gap-4">
        <details open>
          <summary className="cursor-pointer text-sm font-semibold text-night">Comprendre un coup</summary>
          <div className="mt-3 grid gap-3">
            <button
              type="button"
              onClick={() => lastMoveForReview && reviewStoredMove(lastMoveForReview)}
              disabled={!lastMoveForReview || reviewLoading}
              className="rounded border border-line bg-white px-3 py-2 text-sm font-semibold text-night disabled:cursor-not-allowed disabled:opacity-50"
            >
              {reviewLoading ? "Analyse..." : lastMoveForReview?.source === "bot" ? "Comprendre le coup adverse" : "Comprendre le dernier coup"}
            </button>
            {lastReview || reviewLoading || reviewError ? <LastMoveReviewPanel review={lastReview} loading={reviewLoading} error={reviewError} /> : null}
          </div>
        </details>

        <details>
          <summary className="cursor-pointer text-sm font-semibold text-night">Commandes et reglages</summary>
          <div className="mt-3">
            <GameControls
              orientation={orientation}
              onOrientationChange={setOrientation}
              mode={mode}
              onModeChange={setMode}
              onUndo={undo}
              onReset={reset}
              onCopyFen={copyFen}
              onCopyPgn={copyPgn}
            />
          </div>
        </details>

        <details>
          <summary className="cursor-pointer text-sm font-semibold text-night">Historique</summary>
          <div className="mt-3">
            <MoveHistory moves={history} reviews={reviewsByPly} onMoveClick={handleHistoryClick} />
          </div>
        </details>

        <details>
          <summary className="cursor-pointer text-sm font-semibold text-night">Glossaire</summary>
          <div className="mt-3">
            <GlossaryPanel />
          </div>
        </details>

        <details>
          <summary className="cursor-pointer text-sm font-semibold text-night">Details techniques</summary>
          <div className="mt-3 grid gap-2 break-words text-sm text-neutral-700">
            <p>FEN : {fen}</p>
            <p>PGN : {pgn || "*"}</p>
            <p>Coups UCI : {historyUci.join(" ") || "aucun"}</p>
          </div>
        </details>
      </div>
    </aside>
  );
}
