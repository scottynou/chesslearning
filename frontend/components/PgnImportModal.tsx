"use client";

import { Chess } from "chess.js";
import { useState } from "react";

type Props = {
  onImport: (historyUci: string[], side: "white" | "black") => void;
  onClose: () => void;
};

export function PgnImportModal({ onImport, onClose }: Props) {
  const [pgnText, setPgnText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [side, setSide] = useState<"white" | "black">("white");

  function handleImport() {
    if (!pgnText.trim()) {
      setError("Colle un PGN dans la zone de texte.");
      return;
    }
    try {
      const game = new Chess();
      game.loadPgn(pgnText.trim());
      const moves = game.history({ verbose: true });
      const historyUci = moves.map((move) => `${move.from}${move.to}${move.promotion ?? ""}`);
      if (historyUci.length === 0) {
        setError("Le PGN ne contient aucun coup.");
        return;
      }
      onImport(historyUci, side);
    } catch (err) {
      setError(err instanceof Error ? err.message : "PGN invalide.");
    }
  }

  return (
    <div className="post-game-review-overlay" role="dialog" aria-modal="true" aria-label="Importer un PGN">
      <div className="plan-switch-modal">
        <header className="plan-switch-header">
          <h3>Importer un PGN</h3>
          <button type="button" className="saved-games-close" onClick={onClose} aria-label="Fermer">
            ✕
          </button>
        </header>
        <p className="plan-switch-note">Colle un PGN copie depuis chess.com, Lichess ou un autre site.</p>
        <textarea
          value={pgnText}
          onChange={(e) => setPgnText(e.target.value)}
          rows={8}
          placeholder='1. e4 e5 2. Nf3 Nc6 ...'
          className="pgn-import-textarea"
        />
        <div className="pgn-import-side">
          <label>
            <input type="radio" name="pgn-side" value="white" checked={side === "white"} onChange={() => setSide("white")} />
            Je joue les blancs
          </label>
          <label>
            <input type="radio" name="pgn-side" value="black" checked={side === "black"} onChange={() => setSide("black")} />
            Je joue les noirs
          </label>
        </div>
        {error ? <p className="pgn-import-error">{error}</p> : null}
        <button type="button" className="pgn-import-button" onClick={handleImport}>
          Importer
        </button>
      </div>
    </div>
  );
}
