"use client";

import { Chess } from "chess.js";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ChessCoachBoard } from "./ChessCoachBoard";
import {
  ALL_THEMES,
  labelForTheme,
  shuffledPuzzles,
  type Puzzle,
  type PuzzleTheme
} from "@/lib/puzzles";

type Status = "idle" | "correct" | "wrong";

type Props = {
  onClose?: () => void;
};

const STORAGE_KEY = "chess_learner_puzzle_stats_v1";

type Stats = {
  attempted: number;
  solved: number;
  byTheme: Record<PuzzleTheme, { attempted: number; solved: number }>;
};

const EMPTY_STATS: Stats = {
  attempted: 0,
  solved: 0,
  byTheme: ALL_THEMES.reduce(
    (acc, theme) => ({ ...acc, [theme]: { attempted: 0, solved: 0 } }),
    {} as Record<PuzzleTheme, { attempted: number; solved: number }>
  )
};

function loadStats(): Stats {
  if (typeof window === "undefined") return EMPTY_STATS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return EMPTY_STATS;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return EMPTY_STATS;
    const merged: Stats = { ...EMPTY_STATS, ...parsed };
    merged.byTheme = { ...EMPTY_STATS.byTheme, ...(parsed.byTheme ?? {}) };
    return merged;
  } catch {
    return EMPTY_STATS;
  }
}

function saveStats(stats: Stats): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(stats));
  } catch {
    // ignore quota errors
  }
}

export function TacticalTrainingPanel({ onClose }: Props) {
  const [queue, setQueue] = useState<Puzzle[]>([]);
  const [index, setIndex] = useState(0);
  const [status, setStatus] = useState<Status>("idle");
  const [boardWidth, setBoardWidth] = useState(360);
  const [stats, setStats] = useState<Stats>(EMPTY_STATS);
  const [showHint, setShowHint] = useState(false);

  useEffect(() => {
    setQueue(shuffledPuzzles());
    setStats(loadStats());
  }, []);

  useEffect(() => {
    function onResize() {
      setBoardWidth(Math.min(420, Math.max(240, window.innerWidth - 80)));
    }
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const currentPuzzle = queue[index];
  const sideToMove = useMemo(() => {
    if (!currentPuzzle) return "white" as const;
    try {
      const board = new Chess(currentPuzzle.fen);
      return board.turn() === "w" ? ("white" as const) : ("black" as const);
    } catch {
      return "white" as const;
    }
  }, [currentPuzzle]);

  const handleDrop = useCallback(
    (from: string, to: string) => {
      if (!currentPuzzle || status !== "idle") return false;
      const playedUci = `${from}${to}`;
      const expectedBase = currentPuzzle.bestMoveUci.slice(0, 4);
      const correct = playedUci === expectedBase;
      const next: Stats = {
        attempted: stats.attempted + 1,
        solved: stats.solved + (correct ? 1 : 0),
        byTheme: {
          ...stats.byTheme,
          [currentPuzzle.theme]: {
            attempted: (stats.byTheme[currentPuzzle.theme]?.attempted ?? 0) + 1,
            solved: (stats.byTheme[currentPuzzle.theme]?.solved ?? 0) + (correct ? 1 : 0)
          }
        }
      };
      setStats(next);
      saveStats(next);
      setStatus(correct ? "correct" : "wrong");
      return correct;
    },
    [currentPuzzle, stats, status]
  );

  const goNext = useCallback(() => {
    setStatus("idle");
    setShowHint(false);
    if (index + 1 >= queue.length) {
      setQueue(shuffledPuzzles());
      setIndex(0);
    } else {
      setIndex(index + 1);
    }
  }, [index, queue.length]);

  if (!currentPuzzle) {
    return (
      <div className="tactical-panel">
        <p>Chargement…</p>
      </div>
    );
  }

  const successRate = stats.attempted > 0 ? Math.round((stats.solved / stats.attempted) * 100) : 0;

  return (
    <div className="tactical-panel">
      <header className="tactical-header">
        <div>
          <h3>Entraînement tactique</h3>
          <p className="tactical-subtitle">
            {currentPuzzle.themeLabel} · Difficulté {"★".repeat(currentPuzzle.difficulty)}
          </p>
        </div>
        {onClose ? (
          <button type="button" className="saved-games-close" onClick={onClose} aria-label="Fermer">
            ✕
          </button>
        ) : null}
      </header>

      <div className="tactical-stats">
        <span>
          {stats.solved}/{stats.attempted} résolus
        </span>
        <span>{successRate}% de réussite</span>
      </div>

      <p className="tactical-todo">
        À toi de jouer ({sideToMove === "white" ? "Blancs" : "Noirs"}). Trouve le coup gagnant.
      </p>

      <div className="tactical-board-wrap">
        <ChessCoachBoard
          fen={currentPuzzle.fen}
          boardWidth={boardWidth}
          orientation={sideToMove}
          selectedSquare={null}
          legalTargets={[]}
          highlightedMove={null}
          lastMove={null}
          onDrop={(from, to) => handleDrop(from, to)}
          onSquareClick={() => {}}
        />
      </div>

      {status === "idle" && showHint ? (
        <p className="tactical-hint">💡 {currentPuzzle.hint}</p>
      ) : null}

      {status === "correct" ? (
        <div className="tactical-feedback tactical-feedback--ok">
          <strong>✓ Bien joué !</strong>
          <p>{currentPuzzle.explanation}</p>
        </div>
      ) : null}

      {status === "wrong" ? (
        <div className="tactical-feedback tactical-feedback--ko">
          <strong>✗ Pas le bon coup.</strong>
          <p>
            La solution était <code>{currentPuzzle.bestMoveUci}</code>. {currentPuzzle.explanation}
          </p>
        </div>
      ) : null}

      <div className="tactical-actions">
        {status === "idle" && !showHint ? (
          <button type="button" className="tactical-secondary" onClick={() => setShowHint(true)}>
            Indice
          </button>
        ) : null}
        {status !== "idle" ? (
          <button type="button" className="tactical-primary" onClick={goNext}>
            Puzzle suivant →
          </button>
        ) : (
          <button type="button" className="tactical-secondary" onClick={goNext}>
            Passer
          </button>
        )}
      </div>
    </div>
  );
}
