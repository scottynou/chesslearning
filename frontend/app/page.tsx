"use client";

import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Chess, Move, Square } from "chess.js";
import { Menu, X } from "lucide-react";
import { ChessCoachBoard } from "@/components/ChessCoachBoard";
import { GameControls } from "@/components/GameControls";
import { GlossaryPanel } from "@/components/GlossaryPanel";
import { LastMoveReviewPanel } from "@/components/LastMoveReviewPanel";
import { MoveHistory } from "@/components/MoveHistory";
import { OpeningRepertoirePanel } from "@/components/OpeningRepertoirePanel";
import { PlanFirstPanel } from "@/components/PlanFirstPanel";
import { SideSelectionPanel } from "@/components/SideSelectionPanel";
import { getPlanRecommendations, listAvailablePlans, requestBotMove, reviewMove } from "@/lib/api";
import { notationFromUci } from "@/lib/beginnerNotation";
import { canMoveInMode, gameStatus, isPromotionAttempt, tryMove } from "@/lib/chess";
import {
  DEFAULT_BASE_ELO,
  effectiveElo,
  nextAdaptiveBoost,
  nextStablePlyCount,
  normalizeAdaptiveBoost,
  normalizeBaseElo,
  skillLevelForElo
} from "@/lib/eloAdaptation";
import { getOpeningImageSrc } from "@/lib/openingVisuals";
import type {
  Orientation,
  PlanRecommendation,
  PlanRecommendationsResponse,
  PlayMode,
  ReviewMoveResponse,
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
  selectedPlanId: string | null;
  moveHistoryUci: string[];
};

type AppStage = "side-selection" | "white-plan-selection" | "black-first-move" | "black-plan-selection" | "plan-intro" | "coach";
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
  baseElo: number;
  adaptiveBoost: number;
  autoEloEnabled: boolean;
};

const INTERNAL_MAX_MOVES = 5;
const INTERNAL_ENGINE_DEPTH = 8;
const NAVIGATION_KEY = "chess-learning-navigation";
const ELO_SETTINGS_KEY = "chess-learning-elo-settings";

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
  if (view === "plan-intro") {
    return createNavigationSnapshot({
      appStage: "plan-intro",
      userSide,
      orientation: userSide === "black" ? "black" : "white",
      selectedPlanId: plan,
      firstOpponentMove: first,
      historyUci: first ? [first] : []
    });
  }
  if (view === "coach") {
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
    baseElo: DEFAULT_BASE_ELO,
    adaptiveBoost: 0,
    autoEloEnabled: true,
    ...overrides
  };
}

function readStoredEloSettings() {
  if (typeof window === "undefined") {
    return { baseElo: DEFAULT_BASE_ELO, autoEloEnabled: true };
  }
  try {
    const raw = window.localStorage.getItem(ELO_SETTINGS_KEY);
    if (!raw) return { baseElo: DEFAULT_BASE_ELO, autoEloEnabled: true };
    const parsed = JSON.parse(raw) as { baseElo?: unknown; autoEloEnabled?: unknown };
    return {
      baseElo: normalizeBaseElo(typeof parsed.baseElo === "number" ? parsed.baseElo : DEFAULT_BASE_ELO),
      autoEloEnabled: typeof parsed.autoEloEnabled === "boolean" ? parsed.autoEloEnabled : true
    };
  } catch {
    return { baseElo: DEFAULT_BASE_ELO, autoEloEnabled: true };
  }
}

function sideForPly(ply: number): "white" | "black" {
  return ply % 2 === 1 ? "white" : "black";
}

function isOpponentMoveForPlan(move: LastMoveForReview, plan: StrategyPlan | null) {
  if (!plan || (plan.side !== "white" && plan.side !== "black")) return false;
  return sideForPly(move.ply) !== plan.side;
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
  } else if (snapshot.appStage === "plan-intro") {
    params.set("view", "plan-intro");
    params.set("side", snapshot.userSide);
    if (snapshot.selectedPlanId) params.set("plan", snapshot.selectedPlanId);
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
  const [lastUserMoveForReview, setLastUserMoveForReview] = useState<LastMoveForReview | null>(null);
  const [openOpponentReviewPly, setOpenOpponentReviewPly] = useState<number | null>(null);
  const [botThinking, setBotThinking] = useState(false);
  const [botError, setBotError] = useState<string | null>(null);
  const [highlightedMove, setHighlightedMove] = useState<{ from: string; to: string } | null>(null);
  const [highlightedRecommendationUci, setHighlightedRecommendationUci] = useState<string | null>(null);
  const [botStrategyState, setBotStrategyState] = useState<Record<string, unknown>>({});
  const [baseElo, setBaseElo] = useState(DEFAULT_BASE_ELO);
  const [adaptiveBoost, setAdaptiveBoost] = useState(0);
  const [autoEloEnabled, setAutoEloEnabled] = useState(true);
  const [stableEloPlyCount, setStableEloPlyCount] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const navigationReady = useRef(false);
  const skipNextHistoryReplace = useRef(false);
  const skipNextEloPersist = useRef(true);
  const lastEloAdjustmentPly = useRef<number | null>(null);
  const previousEffectiveElo = useRef(DEFAULT_BASE_ELO);

  const fen = game.fen();
  const history = useMemo(() => game.history({ verbose: true }) as VerboseMove[], [game]);
  const status = useMemo(() => gameStatus(game), [game]);
  const pgn = useMemo(() => game.pgn(), [game]);
  const historyUci = useMemo(() => history.map((move) => `${move.from}${move.to}${move.promotion ?? ""}`), [history]);
  const effectiveCoachElo = useMemo(() => effectiveElo(baseElo, autoEloEnabled ? adaptiveBoost : 0), [adaptiveBoost, autoEloEnabled, baseElo]);
  const activeSkillLevel = useMemo(() => skillLevelForElo(effectiveCoachElo), [effectiveCoachElo]);
  const lastBoardMove = useMemo(() => {
    const move = history[history.length - 1];
    return move ? { from: move.from, to: move.to } : null;
  }, [history]);
  const selectedPlan = useMemo(() => {
    return plans.find((plan) => plan.id === selectedPlanId) ?? (planRecommendations?.selectedPlan as StrategyPlan | null) ?? null;
  }, [plans, planRecommendations?.selectedPlan, selectedPlanId]);
  const boardLocked = appStage === "black-plan-selection" || appStage === "white-plan-selection" || appStage === "plan-intro" || appStage === "side-selection";
  const firstMoveLabel = firstOpponentMove ? history[0]?.san ?? firstOpponentMove : null;
  const expectedReplyLabel = useMemo(() => {
    const primary = planRecommendations?.primaryMove;
    const line = selectedPlan?.mainLineUci;
    const linePly = planRecommendations?.planProgress?.linePly ?? historyUci.length;
    if (!primary || !line || line[linePly] !== primary.moveUci) return null;
    const replyUci = line[linePly + 1];
    if (!replyUci) return null;
    const afterPrimary = new Chess(fen);
    try {
      afterPrimary.move({
        from: primary.moveUci.slice(0, 2),
        to: primary.moveUci.slice(2, 4),
        ...(primary.moveUci.slice(4) ? { promotion: primary.moveUci.slice(4) } : {})
      });
      return notationFromUci(afterPrimary.fen(), replyUci).beginnerLabel;
    } catch {
      return `${replyUci.slice(0, 2)} -> ${replyUci.slice(2, 4)}`;
    }
  }, [fen, historyUci.length, planRecommendations?.planProgress?.linePly, planRecommendations?.primaryMove, selectedPlan?.mainLineUci]);
  const latestOpponentReviewMove = useMemo(() => {
    if (appStage !== "coach" || !lastMoveForReview || !selectedPlan) return null;
    return isOpponentMoveForPlan(lastMoveForReview, selectedPlan) ? lastMoveForReview : null;
  }, [appStage, lastMoveForReview, selectedPlan]);
  const latestUserReviewMove = useMemo(() => {
    if (appStage !== "coach" || !lastUserMoveForReview) return null;
    return lastUserMoveForReview;
  }, [appStage, lastUserMoveForReview]);
  const latestOpponentReview = latestOpponentReviewMove ? reviewsByPly[latestOpponentReviewMove.ply] ?? null : null;
  const latestUserReview = latestUserReviewMove ? reviewsByPly[latestUserReviewMove.ply] ?? null : null;
  const opponentReviewOpen = Boolean(latestOpponentReviewMove && openOpponentReviewPly === latestOpponentReviewMove.ply);
  const visibleRecommendations = useMemo(() => {
    const primary = planRecommendations?.primaryMove;
    return primary ? [primary, ...(planRecommendations?.adaptedAlternatives ?? [])] : [];
  }, [planRecommendations?.adaptedAlternatives, planRecommendations?.primaryMove]);
  const recommendationArrows = useMemo(
    () =>
      visibleRecommendations.map((move) => ({
        from: move.moveUci.slice(0, 2),
        to: move.moveUci.slice(2, 4),
        color: move.arrowColor
      })),
    [visibleRecommendations]
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
        baseElo,
        adaptiveBoost,
        autoEloEnabled,
        ...overrides
      }),
    [adaptiveBoost, appStage, autoEloEnabled, baseElo, firstOpponentMove, historyUci, mode, orientation, selectedPlanId, userSide]
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
    const storedElo = readStoredEloSettings();
    const snapshotWithElo = snapshot as Partial<NavigationSnapshot>;
    setGame(buildGameFromHistory(snapshot.historyUci));
    setAppStage(snapshot.appStage);
    setUserSide(snapshot.userSide);
    setOrientation(snapshot.orientation);
    setMode(snapshot.mode);
    setSelectedPlanId(snapshot.selectedPlanId);
    setFirstOpponentMove(snapshot.firstOpponentMove);
    setBaseElo(normalizeBaseElo(snapshotWithElo.baseElo ?? storedElo.baseElo));
    setAutoEloEnabled(snapshotWithElo.autoEloEnabled ?? storedElo.autoEloEnabled);
    setAdaptiveBoost(normalizeAdaptiveBoost(snapshotWithElo.adaptiveBoost ?? 0));
    setStableEloPlyCount(0);
    lastEloAdjustmentPly.current = null;
    setSelectedSquare(null);
    setPendingPromotion(null);
    setLastMessage(null);
    if (snapshot.appStage === "side-selection" || snapshot.appStage === "black-first-move") {
      setPlans([]);
    }
    setPlansError(null);
    setPlanRecommendations(null);
    setPlanError(null);
    setLastReview(null);
    setReviewsByPly({});
    setReviewLoading(false);
    setReviewError(null);
    setLastMoveForReview(null);
    setLastUserMoveForReview(null);
    setOpenOpponentReviewPly(null);
    setBotThinking(false);
    setBotError(null);
    setBotStrategyState({});
    setHighlightedMove(null);
    setHighlightedRecommendationUci(null);
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
    const storedElo = readStoredEloSettings();
    const hydratedSnapshot =
      historySnapshot && typeof historySnapshot.baseElo === "number"
        ? initialSnapshot
        : {
            ...initialSnapshot,
            baseElo: storedElo.baseElo,
            adaptiveBoost: 0,
            autoEloEnabled: storedElo.autoEloEnabled
          };
    restoreNavigationSnapshot(hydratedSnapshot);
    writeNavigationSnapshot(hydratedSnapshot, "replace");
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
    if (typeof window === "undefined") return;
    if (skipNextEloPersist.current) {
      skipNextEloPersist.current = false;
      return;
    }
    window.localStorage.setItem(
      ELO_SETTINGS_KEY,
      JSON.stringify({
        baseElo: normalizeBaseElo(baseElo),
        autoEloEnabled
      })
    );
  }, [autoEloEnabled, baseElo]);

  useEffect(() => {
    if (previousEffectiveElo.current === effectiveCoachElo) return;
    previousEffectiveElo.current = effectiveCoachElo;
    setReviewsByPly({});
    setLastReview(null);
    setReviewError(null);
  }, [effectiveCoachElo]);

  useEffect(() => {
    const primaryUci = planRecommendations?.primaryMove?.moveUci ?? null;
    const hintUci = primaryUci ?? planRecommendations?.expectedOpponentMove?.moveUci ?? null;
    if (appStage !== "coach" || !hintUci) {
      return;
    }
    setHighlightedRecommendationUci(hintUci);
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
    if (appStage !== "white-plan-selection" && appStage !== "black-plan-selection" && appStage !== "plan-intro") {
      return;
    }

    const side = appStage === "white-plan-selection" || (appStage === "plan-intro" && userSide === "white") ? "white" : "black";
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
  }, [appStage, firstOpponentMove, userSide]);

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
      elo: effectiveCoachElo,
      skillLevel: activeSkillLevel,
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
  }, [activeSkillLevel, appStage, effectiveCoachElo, fen, historyUci, selectedPlanId, userSide]);

  const legalTargets = useMemo(() => {
    if (!selectedSquare || boardLocked) return [];
    return game.moves({ square: selectedSquare as Square, verbose: true }).map((move) => move.to);
  }, [boardLocked, game, selectedSquare]);

  const rememberMoveForReview = useCallback(
    (fenBefore: string, fenAfter: string, moveUci: string, ply: number, source: "manual" | "bot", nextHistoryUci: string[]) => {
      const storedMove = { fenBefore, fenAfter, moveUci, ply, source, selectedPlanId, moveHistoryUci: nextHistoryUci };
      setLastMoveForReview(storedMove);
      if (source === "manual") {
        setLastUserMoveForReview(storedMove);
      }
      setLastReview(null);
      setReviewError(null);
      setOpenOpponentReviewPly(null);
    },
    [selectedPlanId]
  );

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
      const nextHistoryUci = [...historyUci, moveUci];
      setGame(result.game);
      setSelectedSquare(null);
      setPendingPromotion(null);
      setBotError(null);
      setHighlightedMove({ from, to });
      setHighlightedRecommendationUci(null);
      rememberMoveForReview(fenBefore, result.game.fen(), moveUci, ply, source, nextHistoryUci);

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
        setLastMessage("Premier coup blanc enregistre. Choisis maintenant une reponse noire adaptee.");
        writeNavigationSnapshot(nextSnapshot, "push");
      } else {
        setLastMessage(null);
      }
      return true;
    },
    [appStage, boardLocked, game, history.length, historyUci, makeNavigationSnapshot, mode, rememberMoveForReview, writeNavigationSnapshot]
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
      elo: effectiveCoachElo,
      skillLevel: activeSkillLevel,
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
        const nextHistoryUci = [...historyUci, response.move.moveUci];
        setGame(result.game);
        setHighlightedMove({ from, to });
        setHighlightedRecommendationUci(null);
        rememberMoveForReview(fenBefore, result.game.fen(), response.move.moveUci, ply, "bot", nextHistoryUci);
      })
      .catch((error: Error) => setBotError(error.message || "Le bot n'a pas pu jouer."))
      .finally(() => {
        if (!cancelled) setBotThinking(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeSkillLevel, appStage, botError, botStrategyState, botThinking, effectiveCoachElo, game, history.length, historyUci, mode, pendingPromotion, rememberMoveForReview, selectedPlanId]);

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
          appStage: "plan-intro",
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

  const startSelectedPlan = useCallback(() => {
    navigateToSnapshot(
      makeNavigationSnapshot({
        appStage: "coach",
        historyUci: userSide === "black" ? historyUci : [],
        firstOpponentMove: userSide === "black" ? firstOpponentMove : null
      })
    );
  }, [firstOpponentMove, historyUci, makeNavigationSnapshot, navigateToSnapshot, userSide]);

  const returnToPlanChoices = useCallback(() => {
    if (userSide === "black") {
      navigateToSnapshot(
        makeNavigationSnapshot({
          appStage: firstOpponentMove ? "black-plan-selection" : "black-first-move",
          selectedPlanId: null,
          historyUci: firstOpponentMove ? historyUci : [],
          firstOpponentMove
        })
      );
      return;
    }
    navigateToSnapshot(
      makeNavigationSnapshot({
        appStage: "white-plan-selection",
        userSide: "white",
        orientation: "white"
      })
    );
  }, [firstOpponentMove, historyUci, makeNavigationSnapshot, navigateToSnapshot, userSide]);

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
      reviewMove({
        fenBefore: move.fenBefore,
        fenAfter: move.fenAfter,
        moveUci: move.moveUci,
        elo: effectiveCoachElo,
        moveHistoryPgn: pgn,
        selectedPlanId: move.selectedPlanId,
        moveHistoryUci: move.moveHistoryUci
      })
        .then((review) => {
          setLastReview(review);
          setReviewsByPly((current) => ({ ...current, [move.ply]: review }));
        })
        .catch((error: Error) => setReviewError(error.message || "Impossible d'analyser ce coup."))
        .finally(() => setReviewLoading(false));
    },
    [effectiveCoachElo, pgn]
  );

  useEffect(() => {
    if (!latestUserReviewMove || reviewsByPly[latestUserReviewMove.ply] || reviewLoading) return;
    reviewStoredMove(latestUserReviewMove);
  }, [latestUserReviewMove, reviewLoading, reviewStoredMove, reviewsByPly]);

  useEffect(() => {
    if (!latestOpponentReviewMove || reviewsByPly[latestOpponentReviewMove.ply] || reviewLoading) return;
    reviewStoredMove(latestOpponentReviewMove);
  }, [latestOpponentReviewMove, reviewLoading, reviewStoredMove, reviewsByPly]);

  useEffect(() => {
    if (!autoEloEnabled || !latestUserReviewMove || !latestUserReview) return;

    const primary = planRecommendations?.primaryMove;
    const hasDanger = Boolean(planRecommendations?.blockedExpectedMove || primary?.warning);
    const nextStableCount = nextStablePlyCount({
      currentStablePlyCount: stableEloPlyCount,
      quality: latestUserReview.quality,
      hasDanger
    });
    const nextBoost = nextAdaptiveBoost({
      currentBoost: adaptiveBoost,
      autoEnabled: autoEloEnabled,
      playerReviewQuality: latestUserReview.quality,
      phaseStatus: planRecommendations?.phaseStatus,
      primaryWarning: primary?.warning ?? planRecommendations?.blockedExpectedMove?.reason ?? null,
      primaryEngineScore: primary?.engineScore ?? null,
      primaryTacticalRisk: primary?.tacticalRisk ?? null,
      stablePlyCount: nextStableCount,
      currentPly: latestUserReviewMove.ply,
      lastAdjustedPly: lastEloAdjustmentPly.current
    });

    if (lastEloAdjustmentPly.current === latestUserReviewMove.ply) return;
    lastEloAdjustmentPly.current = latestUserReviewMove.ply;
    setStableEloPlyCount(nextStableCount);
    if (nextBoost !== adaptiveBoost) {
      setAdaptiveBoost(nextBoost);
    }
  }, [adaptiveBoost, autoEloEnabled, latestUserReview, latestUserReviewMove, planRecommendations?.blockedExpectedMove, planRecommendations?.phaseStatus, planRecommendations?.primaryMove, stableEloPlyCount]);

  const handleBaseEloChange = useCallback((value: number) => {
    setBaseElo(normalizeBaseElo(value));
  }, []);

  const handleAutoEloEnabledChange = useCallback((enabled: boolean) => {
    setAutoEloEnabled(enabled);
    if (!enabled) {
      setAdaptiveBoost(0);
      setStableEloPlyCount(0);
      lastEloAdjustmentPly.current = null;
    }
  }, []);

  const resetAdaptiveBoost = useCallback(() => {
    setAdaptiveBoost(0);
    setStableEloPlyCount(0);
    lastEloAdjustmentPly.current = null;
  }, []);

  function resetBoardOnly() {
    setGame(new Chess());
    setSelectedSquare(null);
    setPendingPromotion(null);
    setHighlightedMove(null);
    setHighlightedRecommendationUci(null);
    setReviewsByPly({});
    setLastReview(null);
    setLastMoveForReview(null);
    setLastUserMoveForReview(null);
    setOpenOpponentReviewPly(null);
    setLastMessage(null);
    setPlanRecommendations(null);
    resetAdaptiveBoost();
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
    setLastUserMoveForReview(null);
    setOpenOpponentReviewPly(null);
    setStableEloPlyCount(0);
    lastEloAdjustmentPly.current = null;
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
        source: "manual",
        selectedPlanId,
        moveHistoryUci: historyUci.slice(0, ply)
      });
      setMenuOpen(true);
    }
  }

  const renderShell = (content: ReactNode) => (
    <>
      <SiteHeader status={appStage === "side-selection" ? null : status} menuOpen={menuOpen} onHome={goHome} onToggleMenu={() => setMenuOpen((open) => !open)} />
      {menuOpen ? (
        <SiteMenu status={status} onHome={goHome} onClose={() => setMenuOpen(false)}>
          {appStage === "side-selection" ? (
            <HomeMenuContent />
          ) : (
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
            <p className="answer-line">Joue le coup blanc sur le plateau. Les reponses noires adaptees apparaissent juste apres.</p>
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
            intro={isBlack ? "Choisis une structure simple a apprendre contre ce premier coup." : "Choisis un plan clair. Le coach l'installe ensuite coup par coup."}
            mode={isBlack ? "black-reply" : "opening"}
            firstMoveLabel={firstMoveLabel}
          />
      </main>
    );
  }

  if (appStage === "plan-intro") {
    return renderShell(
      <main className="plan-intro-page">
        <PlanIntroScreen
          plan={selectedPlan}
          loading={plansLoading}
          error={plansError}
          userSide={userSide}
          firstMoveLabel={firstMoveLabel}
          onBack={returnToPlanChoices}
          onStart={startSelectedPlan}
        />
      </main>
    );
  }

  return renderShell(
    <>
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
            <button type="button" onClick={undo} className="control-button">Annuler</button>
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
            highlightedMoveUci={highlightedRecommendationUci}
            expectedReplyLabel={expectedReplyLabel}
            eloControl={{
              baseElo,
              adaptiveBoost: autoEloEnabled ? adaptiveBoost : 0,
              effectiveElo: effectiveCoachElo,
              autoEnabled: autoEloEnabled,
              onBaseEloChange: handleBaseEloChange,
              onAutoEnabledChange: handleAutoEloEnabledChange,
              onResetBoost: resetAdaptiveBoost
            }}
            onToggleRecommendation={handlePlanRecommendationToggle}
          />
          {latestOpponentReviewMove ? (
            <OpponentMoveInsight
              open={opponentReviewOpen}
              review={latestOpponentReview}
              loading={reviewLoading && !latestOpponentReview}
              error={reviewError}
              onOpen={() => setOpenOpponentReviewPly(latestOpponentReviewMove.ply)}
              onClose={() => setOpenOpponentReviewPly(null)}
              onRetry={() => reviewStoredMove(latestOpponentReviewMove)}
            />
          ) : null}
        </section>
      </main>
    </>
  );
}

function OpponentMoveInsight({
  open,
  review,
  loading,
  error,
  onRetry,
  onOpen,
  onClose
}: {
  open: boolean;
  review: ReviewMoveResponse | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onOpen: () => void;
  onClose: () => void;
}) {
  if (!open) {
    return (
      <button type="button" onClick={onOpen} className="opponent-review-trigger">
        Comprendre le coup adverse
      </button>
    );
  }

  return (
    <section className="opponent-review-dialog is-inline" aria-labelledby="opponent-review-title">
      <div className="opponent-review-head">
        <p>Coup adverse</p>
        <h2 id="opponent-review-title">Ce que ca change</h2>
      </div>

        {loading && !review ? (
          <div className="opponent-review-loading" role="status">
            <span className="coach-spinner" aria-hidden="true" />
            <p>Analyse du coup adverse...</p>
          </div>
        ) : null}

        {error ? (
          <div className="opponent-review-error">
            <p>{error}</p>
            <button type="button" onClick={onRetry} className="opening-detail-toggle">
              Reessayer
            </button>
          </div>
        ) : null}

        {review ? (
          <div className="opponent-review-body">
            <div className="opponent-review-summary">
              <span>Coup joue</span>
              <strong>{review.moveLabel}</strong>
              <small>{review.qualityLabel} - {review.playedMoveEvalLabel} - {review.analysisProvider}</small>
            </div>

            <ReviewNote title="Analyse coach" body={review.coachNarrative} />

            {review.bestMoveWasDifferent ? (
              <div className="opponent-review-best">
                <span>Meilleur repere adverse</span>
                <strong>{review.bestMoveLabel}</strong>
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="opponent-review-actions">
          {!review && !loading ? (
            <button type="button" onClick={onRetry} className="control-button">
              Analyser ce coup
            </button>
          ) : null}
          <button type="button" onClick={onClose} className="opening-detail-toggle">
            Fermer
          </button>
        </div>
    </section>
  );
}

function ReviewNote({ title, body }: { title: string; body: string }) {
  return (
    <article className="opponent-review-note">
      <h3>{title}</h3>
      <p>{body}</p>
    </article>
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

function HomeMenuContent() {
  return (
    <div className="grid gap-4">
      <details open className="site-menu-details">
        <summary>Glossaire</summary>
        <div className="mt-3">
          <GlossaryPanel compact />
        </div>
      </details>

      <details className="site-menu-details">
        <summary>Comment l&apos;utiliser</summary>
        <div className="mt-3 grid gap-2 text-sm leading-6 text-neutral-700">
          <p>Choisis d&apos;abord ton camp, puis une ouverture. Le coach t&apos;aide ensuite a suivre ce plan sur l&apos;echiquier interne.</p>
          <p>Avec les noirs, joue d&apos;abord le premier coup blanc pour obtenir des reponses coherentes.</p>
          <p>Les details moteur restent caches pour garder l&apos;interface lisible.</p>
        </div>
      </details>
    </div>
  );
}

function PlanIntroScreen({
  plan,
  loading,
  error,
  userSide,
  firstMoveLabel,
  onBack,
  onStart
}: {
  plan: StrategyPlan | null;
  loading: boolean;
  error: string | null;
  userSide: UserSide;
  firstMoveLabel: string | null;
  onBack: () => void;
  onStart: () => void;
}) {
  if (loading && !plan) {
    return <section className="panel w-full max-w-3xl text-sm text-neutral-700">Chargement du plan...</section>;
  }
  if (error) {
    return <section className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</section>;
  }
  if (!plan) {
    return (
      <section className="panel w-full max-w-3xl">
        <h1 className="text-2xl font-semibold text-night">Plan introuvable</h1>
        <button type="button" onClick={onBack} className="control-button mt-4">
          Retour
        </button>
      </section>
    );
  }

  const isBlackReply = userSide === "black";
  const teaching = buildPlanTeaching(plan, isBlackReply, firstMoveLabel);
  const ideas = (plan.whatYouWillLearn ?? plan.coreIdeas).slice(0, 3);
  const missions = plan.pieceMissions.slice(0, 3);
  const successCriteria = (plan.successCriteria?.length ? plan.successCriteria : defaultSuccessCriteria()).slice(0, 3);
  const imageSrc = getOpeningImageSrc(plan);

  return (
    <section className="plan-intro-shell">
      <div className="plan-intro-topbar">
        <button type="button" onClick={onBack} className="control-button">
          Retour aux options
        </button>
        <span>{isBlackReply ? "Plan noir verrouille" : "Plan blanc verrouille"}</span>
      </div>

      <article className="plan-intro-hero">
        <div className="plan-intro-copy">
          <p className="plan-intro-kicker">{isBlackReply ? "Reponse choisie" : "Ouverture choisie"}</p>
          <h1>{plan.nameFr}</h1>
          <p className="plan-intro-lead">{compactTeachingText(teaching.lead, 260)}</p>

          <div className="plan-intro-meta">
            {plan.style.slice(0, 3).map((style) => (
              <span key={style}>{style}</span>
            ))}
            {plan.eco.slice(0, 2).map((eco) => (
              <span key={eco}>{eco}</span>
            ))}
          </div>
        </div>

        <div className="plan-intro-visual" aria-label={`Identite visuelle de ${plan.nameFr}`}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={imageSrc} alt="" className="plan-intro-image" />
          <div className="plan-intro-visual-note">
            <span>Plan</span>
            <strong>{plan.mainLineUci.length ? `${plan.mainLineUci.length} coups de repere` : "Plan flexible"}</strong>
          </div>
        </div>
      </article>

      <div className="plan-intro-grid is-compact">
        <section className="plan-story-card">
          <p className="plan-section-kicker">Objectif</p>
          <h2>{teaching.title}</h2>
          <p>{compactTeachingText(plan.learningGoal ?? plan.beginnerGoal, 190)}</p>
        </section>

        <section className="plan-story-card">
          <p className="plan-section-kicker">Reperes</p>
          <h2>Garde seulement ces idees</h2>
          <ul className="plan-check-list">
            {ideas.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>

        <section className="plan-story-card">
          <p className="plan-section-kicker">Signal vert</p>
          <h2>Tu es bien parti si...</h2>
          <ul className="plan-check-list">
            {successCriteria.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>

        <section className="plan-story-card">
          <p className="plan-section-kicker">A eviter</p>
          <h2>{teaching.question}</h2>
          <p>{compactTeachingText(teaching.warning || teaching.answer, 180)}</p>
        </section>
      </div>

      {missions.length ? (
        <section className="plan-path-panel is-compact">
          <div className="plan-path-heading">
            <p className="plan-section-kicker">Pieces</p>
            <h2>Missions utiles</h2>
          </div>
          <div className="plan-mission-grid">
            {missions.map((mission) => (
              <p key={`${mission.piece}-${mission.mission}`}>
                <strong>{mission.piece}</strong>
                <span>{mission.mission}</span>
              </p>
            ))}
          </div>
        </section>
      ) : null}

      <div className="plan-intro-actions">
        <button type="button" onClick={onBack} className="control-button">
          Changer d&apos;option
        </button>
        <button type="button" onClick={onStart} className="plan-start-button">
          OK, commencer
        </button>
      </div>
    </section>
  );
}

function buildPlanTeaching(plan: StrategyPlan, isBlackReply: boolean, firstMoveLabel: string | null) {
  const planName = plan.nameFr;
  const intro = introReasonForPlan(plan, isBlackReply, firstMoveLabel);
  const mainGoal = plan.learningGoal ?? plan.beginnerGoal;
  const core = plan.coreIdeas[0] ?? mainGoal;
  const style = plan.style.slice(0, 2).join(" et ");
  const firstMove = firstMoveLabel ? ` apres ${firstMoveLabel}` : "";
  const sideFrame = isBlackReply
    ? `Avec ${planName}, tu ne cherches pas seulement a survivre${firstMove}. Tu choisis une structure qui donne aux noirs une maniere stable de contester le centre blanc, de sortir les pieces et de rejoindre un milieu de partie que tu comprends.`
    : `Avec ${planName}, tu ne joues pas une suite de coups par coeur. Tu construis une position reconnaissable : un centre coherent, des pieces qui sortent avec une mission, puis un roi assez en securite pour jouer le milieu de partie.`;

  const special: Record<string, Partial<ReturnType<typeof baseTeaching>>> = {
    italian_game_beginner: {
      title: "Developper vite, viser f7, puis roquer",
      question: "Pourquoi le fou va-t-il souvent en c4 ?",
      answer: "Depuis c4, le fou regarde f7, une case fragile au debut parce qu'elle est surtout defendue par le roi noir. Cela ne veut pas dire attaquer tout de suite : cela force surtout les noirs a respecter cette pression pendant que tu termines ton developpement.",
      warning: "Le piege est de vouloir attaquer f7 trop tot. Si ton roi n'est pas roque ou si tes pieces dorment encore, l'attaque peut devenir artificielle."
    },
    london_system_beginner: {
      title: "Construire un setup stable avant de choisir l'attaque",
      question: "Pourquoi sortir le fou en f4 avant e3 ?",
      answer: "Si tu joues e3 trop tot, le fou c1 peut rester enferme. En le sortant d'abord vers f4, tu gardes une piece active qui controle e5 et participe au plan contre le roi noir.",
      warning: "Le piege est de jouer le meme setup sans regarder l'adversaire. Le London est stable, mais il faut quand meme verifier les ruptures noires comme ...c5 ou ...Qb6."
    },
    queens_gambit_beginner: {
      title: "Mettre la pression sur d5 sans chercher un piege",
      question: "Est-ce vraiment un gambit ?",
      answer: "Pas vraiment dans l'esprit debutant : c4 attaque d5 et demande aux noirs comment ils veulent tenir le centre. Si les noirs prennent en c4, les blancs cherchent souvent a recuperer ce pion apres avoir developpe les pieces.",
      warning: "Le piege est de courir apres le pion c4 trop vite. Tu veux d'abord garder ton centre, developper et reprendre dans de bonnes conditions."
    },
    caro_kann_beginner: {
      title: "Construire solide, puis frapper le centre blanc",
      question: "Pourquoi jouer ...c6 avant ...d5 ?",
      answer: "...c6 soutient ...d5. Les noirs laissent les blancs occuper le centre, mais ils preparent une attaque propre contre ce centre sans affaiblir le roi.",
      warning: "Le piege est de devenir trop passif. La Caro-Kann est solide, mais elle doit quand meme attaquer le centre avec ...d5 puis souvent ...c5."
    },
    french_defense_beginner: {
      title: "Accepter moins d'espace pour attaquer la chaine blanche",
      question: "Pourquoi le centre devient-il souvent ferme ?",
      answer: "Apres ...e6 et ...d5, les blancs peuvent avancer e5. La partie devient alors une lutte contre une chaine de pions : les noirs cherchent a attaquer sa base, souvent avec ...c5.",
      warning: "Le piege est d'oublier le fou c8. Si tu enfermes toutes tes pieces derriere tes pions, tu auras une position solide mais difficile a jouer."
    },
    qgd_simplified: {
      title: "Tenir le centre et developper sans panique",
      question: "Pourquoi ...e6 est-il si important ?",
      answer: "...e6 soutient le pion d5 et donne aux noirs une structure fiable. L'objectif n'est pas de tout echanger, mais d'arriver a une position ou les pieces sortent sans faiblesse grave.",
      warning: "Le piege est de subir longtemps le pion c4 blanc. Il faut tenir d5, developper, puis chercher le bon moment pour contester le centre."
    },
    slav_beginner: {
      title: "Soutenir d5 en gardant le fou c8 vivant",
      question: "Pourquoi ...c6 au lieu de ...e6 tout de suite ?",
      answer: "...c6 defend d5 sans bloquer le fou c8. Cela donne aux noirs une structure solide et plus de chances de sortir le fou avant que la position se ferme.",
      warning: "Le piege est de jouer solide sans plan actif. Une Slave reussie garde le centre, mais cherche ensuite ...Bf5 ou ...c5 quand c'est possible."
    },
    kings_indian_setup: {
      title: "Laisser le centre blanc avancer, puis le frapper",
      question: "Pourquoi accepter que les blancs prennent le centre ?",
      answer: "Le fou en g7 et le roque rapide donnent aux noirs une base de contre-attaque. Le centre blanc est impressionnant, mais il devient aussi une cible pour ...e5 ou ...c5.",
      warning: "Le piege est d'attendre trop longtemps. Si tu ne frappes jamais le centre, l'espace blanc peut t'etouffer."
    }
  };

  return {
    ...baseTeaching(planName, intro, mainGoal, core, style, sideFrame),
    ...special[plan.id]
  };
}

function baseTeaching(planName: string, intro: string, mainGoal: string, core: string, style: string, sideFrame: string) {
  return {
    lead: `${intro} ${sideFrame}`,
    title: `Comprendre le fil conducteur de ${planName}`,
    story: `${sideFrame} Le coeur du plan est simple : ${core} Ensuite, chaque coup doit aider cet objectif au lieu d'etre joue parce qu'il ressemble a un coup d'ouverture. ${mainGoal}`,
    question: "Quelle est l'idee a garder en tete ?",
    answer: `Cherche une position ${style || "coherente"} ou tes pieces travaillent ensemble. Si l'adversaire change l'ordre des coups, garde l'objectif principal et adapte seulement le prochain coup.`,
    warning: "Le piege est de jouer les coups du plan sans regarder la position. Si l'adversaire menace quelque chose de concret, il faut d'abord verifier cette menace."
  };
}

function defaultSuccessCriteria() {
  return [
    "La ligne principale ou une branche coherente a ete atteinte.",
    "Le roi est en securite ou la securite du roi est le prochain objectif.",
    "Les pieces mineures principales sont developpees.",
    "Le centre est conteste, clarifie ou stabilise."
  ];
}

function compactTeachingText(value: string, limit: number) {
  const text = value.replace(/\s+/g, " ").trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit).replace(/[\s,.;:!?]+\S*$/, "")}...`;
}

function introReasonForPlan(plan: StrategyPlan, isBlackReply: boolean, firstMoveLabel: string | null) {
  if (!isBlackReply) {
    return plan.shortHistory ?? plan.learningGoal ?? plan.beginnerGoal;
  }
  const prefix = firstMoveLabel ? `Apres ${firstMoveLabel}, ` : "";
  const reasons: Record<string, string> = {
    black_e5_classical:
      "la defense classique e5 remet immediatement un pion au centre. Elle donne une partie ouverte, facile a comprendre : les cavaliers sortent vite, le pion e5 devient le point a defendre, puis le roque arrive naturellement.",
    caro_kann_beginner:
      "la Caro-Kann construit une reponse solide avant de frapper le centre avec ...d5. Elle convient si tu veux un plan calme, une structure claire et moins de tactique immediate.",
    french_defense_beginner:
      "la Francaise prepare ...d5 avec une structure compacte. Elle laisse parfois les blancs avancer, puis le plan noir devient clair : attaquer la chaine de pions blanche.",
    scandinavian_simple:
      "la Scandinave attaque le centre tout de suite avec ...d5. Elle est directe et facile a comprendre, mais il faudra eviter de perdre trop de temps avec la dame.",
    sicilian_dragon_simplified:
      "la Sicilienne conteste le centre depuis le cote avec ...c5. C'est actif et ambitieux, mais plus complexe : le fou en g7 et la pression sur le centre deviennent essentiels.",
    qgd_simplified:
      "la defense dame-pion garde une structure tres stable contre les debuts au pion dame. Elle t'apprend a tenir le centre, developper tranquillement et chercher un bon milieu de partie.",
    slav_beginner:
      "la Slave soutient le pion d5 avec ...c6. Elle garde le centre solide et laisse souvent le fou c8 sortir plus facilement.",
    kings_indian_setup:
      "l'Indienne du roi accepte que les blancs prennent le centre au debut. Les noirs roquent vite, placent le fou en g7, puis attaquent le centre avec ...e5 ou ...c5."
  };
  return `${prefix}${reasons[plan.id] ?? plan.learningGoal ?? plan.beginnerGoal}`;
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
    <div className="grid gap-4">
      <div className="grid gap-4">
        <details open className="site-menu-details">
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

        <details className="site-menu-details">
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
            <MoveHistory moves={history} reviews={reviewsByPly} onMoveClick={handleHistoryClick} />
          </div>
        </details>

        <details className="site-menu-details">
          <summary className="cursor-pointer text-sm font-semibold text-night">Glossaire</summary>
          <div className="mt-3">
            <GlossaryPanel compact />
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
    </div>
  );
}
