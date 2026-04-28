"use client";

import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Chess, Move, Square } from "chess.js";
import { ChevronLeft, ChevronRight, Menu, X } from "lucide-react";
import { ChessCoachBoard } from "@/components/ChessCoachBoard";
import { GameControls } from "@/components/GameControls";
import { MoveHistory } from "@/components/MoveHistory";
import { OpeningRepertoirePanel } from "@/components/OpeningRepertoirePanel";
import { PlanFirstPanel } from "@/components/PlanFirstPanel";
import { SideSelectionPanel } from "@/components/SideSelectionPanel";
import { getPlanRecommendations, listAvailablePlans, requestBotMove } from "@/lib/api";
import { canMoveInMode, gameStatus, isPromotionAttempt, tryMove } from "@/lib/chess";
import { DEFAULT_BASE_ELO, effectiveElo, skillLevelForElo } from "@/lib/eloAdaptation";
import { canStepBack, redoTimeline, undoTimeline, type MoveSource, type TimelineMove } from "@/lib/moveTimeline";
import type { Orientation, PlanRecommendationsResponse, PlayMode, StrategyPlan } from "@/lib/types";

type PendingPromotion = {
  from: string;
  to: string;
};

type VerboseMove = Move & {
  before?: string;
  after?: string;
};

type AppStage = "side-selection" | "white-plan-selection" | "black-first-move" | "black-plan-selection" | "coach";
type UserSide = "white" | "black" | "both";
type NavigationSnapshot = {
  key: "chess-learning-navigation";
  appStage: AppStage;
  userSide: UserSide;
  orientation: Orientation;
  mode: PlayMode;
  selectedPlanId: string | null;
  firstOpponentMove: string | null;
  historyUci: string[];
};

const INTERNAL_MAX_MOVES = 4;
const INTERNAL_ENGINE_DEPTH = 6;
const BOT_ENGINE_DEPTH = 14;
const NAVIGATION_KEY = "chess-learning-navigation";
const PLAYER_ARROW_FALLBACKS = ["rgba(224,185,118,0.82)", "rgba(125,183,154,0.78)", "rgba(126,166,224,0.76)"];
const OPPONENT_EXPECTED_ARROW = "rgba(239,118,118,0.78)";

function buildGameFromHistory(moves: string[]) {
  const next = new Chess();
  for (const move of moves) {
    try {
      next.move({
        from: move.slice(0, 2),
        to: move.slice(2, 4),
        ...(move.slice(4) ? { promotion: move.slice(4) } : {})
      });
    } catch {
      break;
    }
  }
  return next;
}

function isNavigationSnapshot(value: unknown): value is NavigationSnapshot {
  return Boolean(value && typeof value === "object" && (value as NavigationSnapshot).key === NAVIGATION_KEY);
}

function snapshotFromLocation(): NavigationSnapshot {
  const params = new URLSearchParams(window.location.search);
  const view = params.get("view");
  const sideParam = params.get("side");
  const userSide: UserSide = sideParam === "black" || sideParam === "both" ? sideParam : "white";
  const plan = params.get("plan");
  const first = params.get("first");

  if (view === "white-plans") {
    return createNavigationSnapshot({ appStage: "white-plan-selection", userSide: "white", orientation: "white" });
  }
  if (view === "black-first-move") {
    return createNavigationSnapshot({ appStage: "black-first-move", userSide: "black", orientation: "black" });
  }
  if (view === "black-plans") {
    return createNavigationSnapshot({
      appStage: "black-plan-selection",
      userSide: "black",
      orientation: "black",
      firstOpponentMove: first,
      historyUci: first ? [first] : []
    });
  }
  if (view === "coach" || view === "plan-intro") {
    return createNavigationSnapshot({
      appStage: "coach",
      userSide,
      orientation: userSide === "black" ? "black" : "white",
      selectedPlanId: plan,
      firstOpponentMove: first,
      historyUci: first ? [first] : []
    });
  }
  return createNavigationSnapshot();
}

function createNavigationSnapshot(overrides: Partial<NavigationSnapshot> = {}): NavigationSnapshot {
  return {
    key: NAVIGATION_KEY,
    appStage: "side-selection",
    userSide: "white",
    orientation: "white",
    mode: "both",
    selectedPlanId: null,
    firstOpponentMove: null,
    historyUci: [],
    ...overrides
  };
}

function urlForSnapshot(snapshot: NavigationSnapshot) {
  const params = new URLSearchParams();
  if (snapshot.appStage === "white-plan-selection") {
    params.set("view", "white-plans");
  } else if (snapshot.appStage === "black-first-move") {
    params.set("view", "black-first-move");
  } else if (snapshot.appStage === "black-plan-selection") {
    params.set("view", "black-plans");
    if (snapshot.firstOpponentMove) params.set("first", snapshot.firstOpponentMove);
  } else if (snapshot.appStage === "coach") {
    params.set("view", "coach");
    params.set("side", snapshot.userSide);
    if (snapshot.selectedPlanId) params.set("plan", snapshot.selectedPlanId);
    if (snapshot.firstOpponentMove) params.set("first", snapshot.firstOpponentMove);
  }
  const query = params.toString();
  return `${window.location.pathname}${query ? `?${query}` : ""}`;
}

function isAbortError(error: unknown) {
  return error instanceof Error && error.name === "AbortError";
}

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
  const [botThinking, setBotThinking] = useState(false);
  const [botError, setBotError] = useState<string | null>(null);
  const [highlightedMove, setHighlightedMove] = useState<{ from: string; to: string } | null>(null);
  const [botStrategyState, setBotStrategyState] = useState<Record<string, unknown>>({});
  const [moveSources, setMoveSources] = useState<MoveSource[]>([]);
  const [redoStack, setRedoStack] = useState<TimelineMove[]>([]);
  const [adaptiveBoost, setAdaptiveBoost] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const navigationReady = useRef(false);
  const skipNextHistoryReplace = useRef(false);
  const lastEloAdjustmentPly = useRef<number | null>(null);
  const botRequestInFlight = useRef(false);
  const botPausedByTimelineNavigation = useRef(false);
  const timelineRef = useRef<{ historyUci: string[]; moveSources: MoveSource[]; redoStack: TimelineMove[] }>({
    historyUci: [],
    moveSources: [],
    redoStack: []
  });

  const fen = game.fen();
  const history = useMemo(() => game.history({ verbose: true }) as VerboseMove[], [game]);
  const status = useMemo(() => gameStatus(game), [game]);
  const pgn = useMemo(() => game.pgn(), [game]);
  const historyUci = useMemo(() => history.map((move) => `${move.from}${move.to}${move.promotion ?? ""}`), [history]);
  const checkmateResult = useMemo(() => {
    if (!game.isCheckmate()) return null;
    const winner = game.turn() === "w" ? "Les noirs" : "Les blancs";
    const matedKing = game.turn() === "w" ? "blanc" : "noir";
    return {
      winner,
      detail: `Le roi ${matedKing} n'a plus d'echappatoire.`
    };
  }, [game]);
  const effectiveCoachElo = useMemo(() => effectiveElo(DEFAULT_BASE_ELO, adaptiveBoost), [adaptiveBoost]);
  const activeSkillLevel = useMemo(() => skillLevelForElo(effectiveCoachElo), [effectiveCoachElo]);
  const lastBoardMove = useMemo(() => {
    const move = history[history.length - 1];
    return move ? { from: move.from, to: move.to } : null;
  }, [history]);
  const selectedPlan = useMemo(() => {
    return plans.find((plan) => plan.id === selectedPlanId) ?? (planRecommendations?.selectedPlan as StrategyPlan | null) ?? null;
  }, [plans, planRecommendations?.selectedPlan, selectedPlanId]);
  const boardLocked = appStage === "black-plan-selection" || appStage === "white-plan-selection" || appStage === "side-selection";
  const protectedTimelinePlyCount = appStage === "coach" && userSide === "black" && firstOpponentMove ? 1 : 0;
  const canStepBackward = canStepBack(historyUci.length, protectedTimelinePlyCount);
  const canStepForward = !boardLocked && redoStack.length > 0;
  const firstMoveLabel = firstOpponentMove ? history[0]?.san ?? firstOpponentMove : null;
  const visibleRecommendations = useMemo(
    () => planRecommendations?.mergedRecommendations ?? [],
    [planRecommendations?.mergedRecommendations]
  );
  const recommendationArrows = useMemo(
    () => {
      const arrows = visibleRecommendations.map((move, index) => ({
        from: move.moveUci.slice(0, 2),
        to: move.moveUci.slice(2, 4),
        color: move.arrowColor ?? PLAYER_ARROW_FALLBACKS[Math.min(index, PLAYER_ARROW_FALLBACKS.length - 1)]
      }));
      const expectedOpponent = planRecommendations?.expectedOpponentMove;
      if (expectedOpponent) {
        arrows.push({
          from: expectedOpponent.moveUci.slice(0, 2),
          to: expectedOpponent.moveUci.slice(2, 4),
          color: expectedOpponent.arrowColor ?? OPPONENT_EXPECTED_ARROW
        });
      }
      return arrows;
    },
    [planRecommendations?.expectedOpponentMove, visibleRecommendations]
  );
  const makeNavigationSnapshot = useCallback(
    (overrides: Partial<NavigationSnapshot> = {}) =>
      createNavigationSnapshot({
        appStage,
        userSide,
        orientation,
        mode,
        selectedPlanId,
        firstOpponentMove,
        historyUci,
        ...overrides
      }),
    [appStage, firstOpponentMove, historyUci, mode, orientation, selectedPlanId, userSide]
  );

  const writeNavigationSnapshot = useCallback((snapshot: NavigationSnapshot, action: "push" | "replace") => {
    if (typeof window === "undefined") return;
    const url = urlForSnapshot(snapshot);
    if (action === "push") {
      window.history.pushState(snapshot, "", url);
    } else {
      window.history.replaceState(snapshot, "", url);
    }
  }, []);

  const restoreNavigationSnapshot = useCallback((snapshot: NavigationSnapshot) => {
    const restoredMoveSources: MoveSource[] = snapshot.historyUci.map(() => "manual");
    timelineRef.current = { historyUci: snapshot.historyUci, moveSources: restoredMoveSources, redoStack: [] };
    setGame(buildGameFromHistory(snapshot.historyUci));
    setAppStage(snapshot.appStage);
    setUserSide(snapshot.userSide);
    setOrientation(snapshot.orientation);
    setMode(snapshot.mode);
    setSelectedPlanId(snapshot.selectedPlanId);
    setFirstOpponentMove(snapshot.firstOpponentMove);
    setMoveSources(restoredMoveSources);
    setRedoStack([]);
    setAdaptiveBoost(0);
    lastEloAdjustmentPly.current = null;
    botRequestInFlight.current = false;
    botPausedByTimelineNavigation.current = false;
    setSelectedSquare(null);
    setPendingPromotion(null);
    setLastMessage(null);
    if (snapshot.appStage === "side-selection" || snapshot.appStage === "black-first-move") {
      setPlans([]);
    }
    setPlansError(null);
    setPlanRecommendations(null);
    setPlanError(null);
    setBotThinking(false);
    setBotError(null);
    setBotStrategyState({});
    setHighlightedMove(null);
    setMenuOpen(false);
  }, []);

  const navigateToSnapshot = useCallback(
    (snapshot: NavigationSnapshot, action: "push" | "replace" = "push") => {
      restoreNavigationSnapshot(snapshot);
      writeNavigationSnapshot(snapshot, action);
    },
    [restoreNavigationSnapshot, writeNavigationSnapshot]
  );

  useEffect(() => {
    const historySnapshot = isNavigationSnapshot(window.history.state) ? window.history.state : null;
    const initialSnapshot = historySnapshot ?? snapshotFromLocation();
    restoreNavigationSnapshot(initialSnapshot);
    writeNavigationSnapshot(initialSnapshot, "replace");
    navigationReady.current = true;
    skipNextHistoryReplace.current = true;

    function handlePopState(event: PopStateEvent) {
      const snapshot = isNavigationSnapshot(event.state) ? event.state : snapshotFromLocation();
      restoreNavigationSnapshot(snapshot);
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [restoreNavigationSnapshot, writeNavigationSnapshot]);

  useEffect(() => {
    if (!navigationReady.current) return;
    if (skipNextHistoryReplace.current) {
      skipNextHistoryReplace.current = false;
      return;
    }
    writeNavigationSnapshot(makeNavigationSnapshot(), "replace");
  }, [makeNavigationSnapshot, writeNavigationSnapshot]);

  useEffect(() => {
    const primaryUci = planRecommendations?.primaryMove?.moveUci ?? null;
    const hintUci = primaryUci ?? planRecommendations?.expectedOpponentMove?.moveUci ?? null;
    if (appStage !== "coach" || !hintUci) {
      setHighlightedMove(null);
      return;
    }
    setHighlightedMove({ from: hintUci.slice(0, 2), to: hintUci.slice(2, 4) });
  }, [appStage, planRecommendations?.expectedOpponentMove?.moveUci, planRecommendations?.primaryMove?.moveUci]);

  useEffect(() => {
    function updateBoardWidth() {
      const viewportWidth = Math.min(
        window.innerWidth,
        window.outerWidth || window.innerWidth,
        document.documentElement.clientWidth || window.innerWidth,
        window.visualViewport?.width ?? window.innerWidth
      );
      const mobileViewport = viewportWidth <= 540;
      const horizontalReserve = mobileViewport ? 52 : 38;
      const maxBoardWidth = mobileViewport ? 340 : 720;
      const width = Math.min(viewportWidth - horizontalReserve, viewportWidth * 0.9, maxBoardWidth);
      setBoardWidth(Math.floor(Math.max(240, width)));
    }
    updateBoardWidth();
    window.addEventListener("resize", updateBoardWidth);
    return () => window.removeEventListener("resize", updateBoardWidth);
  }, []);

  useEffect(() => {
    if (appStage !== "white-plan-selection" && appStage !== "black-plan-selection") return;

    const side = appStage === "white-plan-selection" ? "white" : "black";
    const firstMove = side === "black" ? firstOpponentMove ?? undefined : undefined;
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
    const controller = new AbortController();
    setPlanLoading(true);
    setPlanError(null);
    getPlanRecommendations({
      fen,
      selectedPlanId,
      elo: effectiveCoachElo,
      skillLevel: activeSkillLevel,
      moveHistoryUci: historyUci,
      maxMoves: INTERNAL_MAX_MOVES,
      engineDepth: INTERNAL_ENGINE_DEPTH,
      signal: controller.signal
    })
      .then((response) => {
        if (active) setPlanRecommendations(response);
      })
      .catch((error: Error) => {
        if (isAbortError(error)) return;
        if (!active) return;
        setPlanRecommendations(null);
        setPlanError(error.message || "Impossible de mettre a jour les coups.");
      })
      .finally(() => {
        if (active) setPlanLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [activeSkillLevel, appStage, effectiveCoachElo, fen, historyUci, selectedPlanId, userSide]);

  useEffect(() => {
    if (appStage !== "coach" || !planRecommendations?.adaptiveSignal) return;
    const currentPly = historyUci.length;
    if (lastEloAdjustmentPly.current === currentPly) return;
    lastEloAdjustmentPly.current = currentPly;

    const delta = planRecommendations.adaptiveSignal.suggestedBoostDelta ?? 0;
    if (!delta) return;
    setAdaptiveBoost((current) => Math.max(0, Math.min(600, current + delta)));
  }, [appStage, historyUci.length, planRecommendations?.adaptiveSignal]);

  const legalTargets = useMemo(() => {
    if (!selectedSquare || boardLocked) return [];
    return game.moves({ square: selectedSquare as Square, verbose: true }).map((move) => move.to);
  }, [boardLocked, game, selectedSquare]);

  const applyMove = useCallback(
    (from: string, to: string, promotion?: string, source: MoveSource = "manual") => {
      if (boardLocked) {
        setLastMessage("Choisis d'abord ton plan avant de continuer la partie.");
        return false;
      }
      if (source === "manual" && !canMoveInMode(game, mode)) {
        setLastMessage("Ce mode ne permet pas de jouer ce camp.");
        return false;
      }

      const result = tryMove(game, from, to, promotion);
      if (!result) {
        setLastMessage("Coup illegal refuse.");
        return false;
      }

      const moveUci = `${from}${to}${promotion ?? ""}`;
      const currentTimeline = timelineRef.current;
      const nextHistoryUci = [...currentTimeline.historyUci, moveUci];
      const nextMoveSources = [...currentTimeline.moveSources.slice(0, currentTimeline.historyUci.length), source];
      timelineRef.current = { historyUci: nextHistoryUci, moveSources: nextMoveSources, redoStack: [] };
      setGame(result.game);
      setMoveSources(nextMoveSources);
      setRedoStack([]);
      if (source === "manual") {
        botPausedByTimelineNavigation.current = false;
      }
      setSelectedSquare(null);
      setPendingPromotion(null);
      setBotError(null);
      setHighlightedMove(null);

      if (appStage === "black-first-move" && history.length === 0 && source === "manual") {
        const nextSnapshot = makeNavigationSnapshot({
          appStage: "black-plan-selection",
          userSide: "black",
          orientation: "black",
          selectedPlanId: null,
          firstOpponentMove: moveUci,
          historyUci: nextHistoryUci
        });
        setFirstOpponentMove(moveUci);
        setAppStage("black-plan-selection");
        setLastMessage("Premier coup blanc enregistre. Choisis maintenant une reponse noire.");
        writeNavigationSnapshot(nextSnapshot, "push");
      } else {
        setLastMessage(null);
      }
      return true;
    },
    [appStage, boardLocked, game, history.length, makeNavigationSnapshot, mode, writeNavigationSnapshot]
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
    if (appStage !== "coach" || (mode !== "white" && mode !== "black")) return;
    if (game.isGameOver() || pendingPromotion || botRequestInFlight.current || botError) return;

    const userTurn = mode === "white" ? game.turn() === "w" : game.turn() === "b";
    if (userTurn || botPausedByTimelineNavigation.current) return;

    let cancelled = false;
    const controller = new AbortController();
    const fenBefore = game.fen();
    botRequestInFlight.current = true;
    setBotThinking(true);
    setBotError(null);

    requestBotMove({
      fen: fenBefore,
      elo: 3200,
      skillLevel: "pro",
      maxMoves: 1,
      engineDepth: BOT_ENGINE_DEPTH,
      botStyle: "balanced",
      selectedBotPlanId: selectedPlanId,
      userPlanId: selectedPlanId,
      strategyState: { ...botStrategyState, moveHistoryUci: historyUci },
      signal: controller.signal
    })
      .then((response) => {
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
        const currentTimeline = timelineRef.current;
        const nextHistoryUci = [...currentTimeline.historyUci, response.move.moveUci];
        const nextMoveSources = [...currentTimeline.moveSources.slice(0, currentTimeline.historyUci.length), "bot" as MoveSource];
        timelineRef.current = { historyUci: nextHistoryUci, moveSources: nextMoveSources, redoStack: [] };
        setGame(result.game);
        setMoveSources(nextMoveSources);
        setRedoStack([]);
        setHighlightedMove(null);
      })
      .catch((error: Error) => {
        if (cancelled || isAbortError(error)) return;
        setBotError(error.message || "Le bot n'a pas pu jouer.");
      })
      .finally(() => {
        if (!cancelled) {
          botRequestInFlight.current = false;
          setBotThinking(false);
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
      botRequestInFlight.current = false;
      setBotThinking(false);
    };
  }, [appStage, botError, botStrategyState, game, historyUci, mode, pendingPromotion, selectedPlanId]);

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
    navigateToSnapshot(
      makeNavigationSnapshot({
        appStage: "white-plan-selection",
        userSide: "white",
        orientation: "white"
      })
    );
  }

  function startBlackFlow() {
    navigateToSnapshot(
      makeNavigationSnapshot({
        appStage: "black-first-move",
        userSide: "black",
        orientation: "black"
      })
    );
  }

  function startFreeMode() {
    navigateToSnapshot(
      makeNavigationSnapshot({
        appStage: "coach",
        userSide: "both",
        orientation: "white"
      })
    );
  }

  const handlePlanSelect = useCallback(
    (planId: string) => {
      const plan = plans.find((item) => item.id === planId);
      const planOrientation: Orientation = plan?.side === "black" ? "black" : "white";
      navigateToSnapshot(
        makeNavigationSnapshot({
          appStage: "coach",
          userSide,
          orientation: planOrientation,
          selectedPlanId: planId,
          historyUci: userSide === "black" ? historyUci : [],
          firstOpponentMove: userSide === "black" ? firstOpponentMove : null
        })
      );
    },
    [firstOpponentMove, historyUci, makeNavigationSnapshot, navigateToSnapshot, plans, userSide]
  );

  const resetAdaptiveBoost = useCallback(() => {
    setAdaptiveBoost(0);
    lastEloAdjustmentPly.current = null;
  }, []);

  function clearPositionDerivedState() {
    setSelectedSquare(null);
    setPendingPromotion(null);
    setHighlightedMove(null);
    setLastMessage(null);
    setPlanRecommendations(null);
    setPlanError(null);
    botRequestInFlight.current = false;
    setBotThinking(false);
    setBotError(null);
    setBotStrategyState({});
    resetAdaptiveBoost();
  }

  function resetBoardOnly() {
    timelineRef.current = { historyUci: [], moveSources: [], redoStack: [] };
    botPausedByTimelineNavigation.current = false;
    setGame(new Chess());
    setMoveSources([]);
    setRedoStack([]);
    clearPositionDerivedState();
  }

  function undo() {
    const currentTimeline = timelineRef.current;
    const timeline = undoTimeline(
      currentTimeline.historyUci,
      currentTimeline.moveSources,
      currentTimeline.redoStack,
      protectedTimelinePlyCount
    );
    if (!timeline.undoneMove) return;

    timelineRef.current = { historyUci: timeline.historyUci, moveSources: timeline.moveSources, redoStack: timeline.redoStack };
    botPausedByTimelineNavigation.current = true;
    setGame(buildGameFromHistory(timeline.historyUci));
    setMoveSources(timeline.moveSources);
    setRedoStack(timeline.redoStack);
    clearPositionDerivedState();

    if (userSide === "black" && timeline.historyUci.length === 0 && appStage !== "coach") {
      setSelectedPlanId(null);
      setFirstOpponentMove(null);
      setPlans([]);
      setAppStage("black-first-move");
    }
  }

  function redo() {
    const currentTimeline = timelineRef.current;
    const timeline = redoTimeline(currentTimeline.redoStack);
    if (!timeline.nextMove || boardLocked) return;

    const { moveUci, source } = timeline.nextMove;
    const baseGame = buildGameFromHistory(currentTimeline.historyUci);
    const result = tryMove(baseGame, moveUci.slice(0, 2), moveUci.slice(2, 4), moveUci.slice(4) || undefined);
    if (!result) {
      timelineRef.current = { ...currentTimeline, redoStack: [] };
      setRedoStack([]);
      setLastMessage("Le coup suivant ne correspond plus a cette position.");
      return;
    }

    const nextHistoryUci = [...currentTimeline.historyUci, moveUci];
    const nextMoveSources = [...currentTimeline.moveSources, source];
    timelineRef.current = { historyUci: nextHistoryUci, moveSources: nextMoveSources, redoStack: timeline.redoStack };
    botPausedByTimelineNavigation.current = true;
    setGame(result.game);
    setMoveSources(nextMoveSources);
    setRedoStack(timeline.redoStack);
    clearPositionDerivedState();
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
    navigateToSnapshot(makeNavigationSnapshot({ appStage: "side-selection", userSide: "white", orientation: "white", selectedPlanId: null, firstOpponentMove: null, historyUci: [] }));
  }

  function goHome() {
    setMenuOpen(false);
    changePlan();
  }

  async function copyText(value: string, label: string) {
    await navigator.clipboard.writeText(value);
    setLastMessage(`${label} copie.`);
  }

  function handleHistoryClick(_ply: number, move: Move) {
    setHighlightedMove({ from: move.from, to: move.to });
  }

  const renderShell = (content: ReactNode) => (
    <>
      <SiteHeader status={appStage === "side-selection" ? null : status} menuOpen={menuOpen} onHome={goHome} onToggleMenu={() => setMenuOpen((open) => !open)} />
      {menuOpen ? (
        <SiteMenu status={status} onHome={goHome} onClose={() => setMenuOpen(false)}>
          {appStage === "side-selection" ? null : (
            <CoachUtilityMenu
              orientation={orientation}
              setOrientation={setOrientation}
              mode={mode}
              setMode={setMode}
              undo={undo}
              reset={reset}
              copyFen={() => copyText(fen, "FEN")}
              copyPgn={() => copyText(pgn || "*", "PGN")}
              history={history}
              handleHistoryClick={handleHistoryClick}
              fen={fen}
              pgn={pgn}
              historyUci={historyUci}
            />
          )}
        </SiteMenu>
      ) : null}
      {content}
    </>
  );

  if (appStage === "side-selection") {
    return renderShell(
      <main>
        <SideSelectionPanel onChooseWhite={startWhiteFlow} onChooseBlack={startBlackFlow} onChooseFreeMode={startFreeMode} />
      </main>
    );
  }

  if (appStage === "black-first-move") {
    return renderShell(
      <main className="first-move-shell">
        <section className="first-move-board">
          <ChessCoachBoard
            fen={fen}
            boardWidth={boardWidth}
            orientation={orientation}
            selectedSquare={selectedSquare}
            legalTargets={legalTargets}
            highlightedMove={highlightedMove}
            lastMove={lastBoardMove}
            onDrop={requestMove}
            onSquareClick={handleSquareClick}
          />
          {lastMessage ? <div className="quiet-alert">{lastMessage}</div> : null}
        </section>
        <section className="first-move-brief">
          <article className="first-move-card">
            <p>Je joue les noirs</p>
            <h1>Premier coup blanc.</h1>
            <p className="answer-line">Joue le coup blanc sur le plateau. Les reponses noires apparaissent juste apres.</p>
          </article>
        </section>
      </main>
    );
  }

  if (appStage === "white-plan-selection" || appStage === "black-plan-selection") {
    const isBlack = appStage === "black-plan-selection";
    return renderShell(
      <main className="plan-selection-shell">
        <div className="plan-selection-topbar">
          <div className="selection-actions">
            <button type="button" onClick={changePlan} className="selection-return-button">
              Retour au choix du camp
            </button>
          </div>
        </div>
        {isBlack ? (
          <section className="plan-selection-board">
            <ChessCoachBoard
              fen={fen}
              boardWidth={Math.min(boardWidth, 220)}
              orientation={orientation}
              selectedSquare={null}
              legalTargets={[]}
              highlightedMove={highlightedMove}
              lastMove={lastBoardMove}
              locked
              onDrop={requestMove}
              onSquareClick={handleSquareClick}
            />
          </section>
        ) : null}
        {plansLoading ? <div className="quiet-alert">Chargement des plans...</div> : null}
        {plansError ? <div className="error-alert">{plansError}</div> : null}
        <OpeningRepertoirePanel
          plans={plans}
          selectedPlanId={selectedPlanId}
          onSelect={handlePlanSelect}
          title={isBlack ? "Reponses noires" : "Ouvertures blanches"}
          mode={isBlack ? "black-reply" : "opening"}
          firstMoveLabel={firstMoveLabel}
        />
      </main>
    );
  }

  return renderShell(
    <main className="coach-live-shell">
      <section className="coach-board-column">
        <div className="coach-board-stage">
          <ChessCoachBoard
            fen={fen}
            boardWidth={boardWidth}
            orientation={orientation}
            selectedSquare={selectedSquare}
            legalTargets={legalTargets}
            highlightedMove={highlightedMove}
            recommendationArrows={recommendationArrows}
            lastMove={lastBoardMove}
            thinking={botThinking}
            onDrop={requestMove}
            onSquareClick={handleSquareClick}
          />

          {checkmateResult ? (
            <div className="checkmate-overlay" role="status" aria-live="polite">
              <span>Echec et mat</span>
              <strong>{checkmateResult.winner} gagnent</strong>
              <p>{checkmateResult.detail}</p>
            </div>
          ) : null}

          {pendingPromotion ? (
            <div className="promotion-popover" role="dialog" aria-label="Choisir une promotion">
              <p>Promotion</p>
              <div>
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
                    className="control-button"
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <div className="coach-board-controls">
          <button
            type="button"
            onClick={undo}
            className="control-button icon-control"
            disabled={!canStepBackward || botThinking}
            aria-label="Coup precedent"
            title="Coup precedent"
          >
            <ChevronLeft size={18} />
          </button>
          <button
            type="button"
            onClick={redo}
            className="control-button icon-control"
            disabled={!canStepForward || botThinking}
            aria-label="Coup suivant"
            title="Coup suivant"
          >
            <ChevronRight size={18} />
          </button>
          <button type="button" onClick={reset} className="control-button">Reset</button>
          <button type="button" onClick={() => setOrientation(orientation === "white" ? "black" : "white")} className="control-button">Tourner</button>
        </div>

        {botError ? <div className="coach-board-error">{botError}</div> : null}
        {lastMessage ? <div className="coach-board-note">{lastMessage}</div> : null}
      </section>

      <section className="coach-panel-column">
        <PlanFirstPanel
          selectedPlan={selectedPlan}
          recommendations={planRecommendations}
          loading={planLoading}
          error={planError}
        />
      </section>
    </main>
  );
}

function SiteHeader({
  status,
  menuOpen,
  onHome,
  onToggleMenu
}: {
  status: string | null;
  menuOpen: boolean;
  onHome: () => void;
  onToggleMenu: () => void;
}) {
  return (
    <header className="site-header">
      <div className="site-header-inner">
        <button type="button" onClick={onHome} className="site-brand" aria-label="Retour a l'accueil Chess Learning">
          <span className="site-brand-mark" aria-hidden="true">
            <span className="site-brand-pawn" />
          </span>
          <span className="site-brand-text">Chess Learning</span>
        </button>
        <div className="site-header-actions">
          {status ? <span className="site-status">{status}</span> : null}
          <button type="button" onClick={onToggleMenu} className="site-menu-button" aria-label={menuOpen ? "Fermer le menu" : "Ouvrir le menu"} aria-expanded={menuOpen}>
            {menuOpen ? <X size={20} strokeWidth={2.1} /> : <Menu size={20} strokeWidth={2.1} />}
          </button>
        </div>
      </div>
    </header>
  );
}

function SiteMenu({ status, onHome, onClose, children }: { status: string; onHome: () => void; onClose: () => void; children: ReactNode }) {
  return (
    <div className="site-menu-layer">
      <button type="button" className="site-menu-backdrop" aria-label="Fermer le menu" onClick={onClose} />
      <aside className="site-menu-popover" aria-label="Menu Chess Learning">
        <div className="site-menu-head">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-clay">Menu</p>
            <h2 className="text-xl font-semibold text-night">Chess Learning</h2>
          </div>
          <button type="button" onClick={onClose} className="site-menu-close" aria-label="Fermer le menu">
            <X size={18} />
          </button>
        </div>

        <div className="grid gap-2">
          <button type="button" onClick={onHome} className="site-menu-row">
            Accueil
          </button>
          <div className="rounded border border-line bg-stone-50 px-3 py-2 text-sm font-semibold text-neutral-700">{status}</div>
        </div>

        {children}
      </aside>
    </div>
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
  history,
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
  history: VerboseMove[];
  handleHistoryClick: (ply: number, move: Move) => void;
  fen: string;
  pgn: string;
  historyUci: string[];
}) {
  return (
    <div className="grid gap-4">
      <details open className="site-menu-details">
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

      <details className="site-menu-details">
        <summary className="cursor-pointer text-sm font-semibold text-night">Historique</summary>
        <div className="mt-3">
          <MoveHistory moves={history} onMoveClick={handleHistoryClick} />
        </div>
      </details>

      <details className="site-menu-details">
        <summary className="cursor-pointer text-sm font-semibold text-night">Details techniques</summary>
        <div className="mt-3 grid gap-2 break-words text-sm text-neutral-700">
          <p>FEN : {fen}</p>
          <p>PGN : {pgn || "*"}</p>
          <p>Coups UCI : {historyUci.join(" ") || "aucun"}</p>
        </div>
      </details>
    </div>
  );
}
