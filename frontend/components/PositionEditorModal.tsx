"use client";

import { useEffect, useMemo, useState } from "react";

import {
  EDITABLE_FILES,
  EDITABLE_RANKS,
  editableBoardFromFen,
  editableBoardToFen,
  emptyEditableBoard,
  inferCastlingRights,
  pieceLabel,
  pieceSymbol,
  type EditableBoard,
  type EditablePiece
} from "@/lib/editableBoard";

type Props = {
  initialFen: string;
  onApply: (fen: string, sideToMove: "white" | "black") => void;
  onClose: () => void;
};

const ALL_PIECES: EditablePiece[] = ["K", "Q", "R", "B", "N", "P", "k", "q", "r", "b", "n", "p"];
const STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export function PositionEditorModal({ initialFen, onApply, onClose }: Props) {
  const [board, setBoard] = useState<EditableBoard>(() => editableBoardFromFen(initialFen));
  const [selectedPiece, setSelectedPiece] = useState<EditablePiece | "erase" | null>(null);
  const [sideToMove, setSideToMove] = useState<"white" | "black">(() =>
    initialFen.split(" ")[1] === "b" ? "black" : "white"
  );

  useEffect(() => {
    setBoard(editableBoardFromFen(initialFen));
    setSideToMove(initialFen.split(" ")[1] === "b" ? "black" : "white");
  }, [initialFen]);

  const fenPreview = useMemo(() => {
    const castling = inferCastlingRights(board);
    return editableBoardToFen(board, sideToMove, castling);
  }, [board, sideToMove]);

  function handleSquareClick(square: string) {
    if (selectedPiece === null) return;
    setBoard((prev) => ({
      ...prev,
      [square]: selectedPiece === "erase" ? null : selectedPiece
    }));
  }

  function clearAll() {
    setBoard(emptyEditableBoard());
  }

  function resetToStart() {
    setBoard(editableBoardFromFen(STARTING_FEN));
    setSideToMove("white");
  }

  function apply() {
    onApply(fenPreview, sideToMove);
  }

  return (
    <div className="post-game-review-overlay" role="dialog" aria-modal="true" aria-label="Éditer la position">
      <div className="position-editor-modal">
        <header className="position-editor-header">
          <h3>Éditer la position</h3>
          <button type="button" className="saved-games-close" onClick={onClose} aria-label="Fermer">
            ✕
          </button>
        </header>

        <p className="position-editor-note">
          Sélectionne une pièce puis clique une case pour la placer. « Effacer » vide une case.
          La position peut être totalement libre.
        </p>

        <div className="position-editor-toolbar">
          {ALL_PIECES.map((piece) => (
            <button
              key={piece}
              type="button"
              className={`position-editor-piece ${selectedPiece === piece ? "is-active" : ""} ${
                piece === piece.toLowerCase() ? "is-black" : "is-white"
              }`}
              onClick={() => setSelectedPiece(piece)}
              title={pieceLabel(piece)}
              aria-label={pieceLabel(piece)}
            >
              {pieceSymbol(piece)}
            </button>
          ))}
          <button
            type="button"
            className={`position-editor-piece is-erase ${selectedPiece === "erase" ? "is-active" : ""}`}
            onClick={() => setSelectedPiece("erase")}
            title="Effacer"
            aria-label="Effacer la case"
          >
            ⌫
          </button>
        </div>

        <div className="position-editor-board" aria-label="Position editable">
          {orientedSquares().map((square) => {
            const fileIndex = EDITABLE_FILES.indexOf(square[0] as (typeof EDITABLE_FILES)[number]);
            const rank = Number(square[1]);
            const isLight = (fileIndex + rank) % 2 === 1;
            const piece = board[square];
            return (
              <button
                key={square}
                type="button"
                className={[
                  "position-editor-square",
                  isLight ? "is-light" : "is-dark",
                  piece ? "has-piece" : ""
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={() => handleSquareClick(square)}
                aria-label={`${square} ${piece ? pieceLabel(piece) : "vide"}`}
              >
                <span className="position-editor-piece-glyph">{pieceSymbol(piece)}</span>
                <small className="position-editor-square-label">{square}</small>
              </button>
            );
          })}
        </div>

        <div className="position-editor-controls">
          <div className="position-editor-side">
            <span>Au trait :</span>
            <button
              type="button"
              className={`position-editor-side-btn ${sideToMove === "white" ? "is-active" : ""}`}
              onClick={() => setSideToMove("white")}
            >
              Blancs
            </button>
            <button
              type="button"
              className={`position-editor-side-btn ${sideToMove === "black" ? "is-active" : ""}`}
              onClick={() => setSideToMove("black")}
            >
              Noirs
            </button>
          </div>
          <div className="position-editor-actions">
            <button type="button" className="tactical-secondary" onClick={clearAll}>
              Tout effacer
            </button>
            <button type="button" className="tactical-secondary" onClick={resetToStart}>
              Position initiale
            </button>
          </div>
        </div>

        <code className="position-editor-fen">{fenPreview}</code>

        <div className="position-editor-validate">
          <button type="button" className="tactical-primary" onClick={apply}>
            Valider la position
          </button>
        </div>
      </div>
    </div>
  );
}

function orientedSquares(): string[] {
  const result: string[] = [];
  for (const rank of EDITABLE_RANKS) {
    for (const file of EDITABLE_FILES) {
      result.push(`${file}${rank}`);
    }
  }
  return result;
}
