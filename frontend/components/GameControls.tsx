"use client";

import { Copy, FlipHorizontal2, RotateCcw, StepBack } from "lucide-react";
import type { Orientation, PlayMode } from "@/lib/types";

type GameControlsProps = {
  orientation: Orientation;
  onOrientationChange: (value: Orientation) => void;
  mode: PlayMode;
  onModeChange: (value: PlayMode) => void;
  onUndo: () => void;
  onReset: () => void;
  onCopyFen: () => void;
  onCopyPgn: () => void;
};

export function GameControls({
  orientation,
  onOrientationChange,
  mode,
  onModeChange,
  onUndo,
  onReset,
  onCopyFen,
  onCopyPgn
}: GameControlsProps) {
  return (
    <div className="game-controls">
      <div className="game-controls-selects">
        <label>
          <span>Orientation</span>
          <select value={orientation} onChange={(event) => onOrientationChange(event.target.value as Orientation)}>
            <option value="white">Blancs</option>
            <option value="black">Noirs</option>
          </select>
        </label>

        <label>
          <span>Mode</span>
          <select value={mode} onChange={(event) => onModeChange(event.target.value as PlayMode)}>
            <option value="both">Jouer les deux camps</option>
            <option value="friend">Reproduire une partie / mode ami</option>
            <option value="white">Seulement blancs vs bot</option>
            <option value="black">Seulement noirs vs bot</option>
          </select>
        </label>
      </div>

      <div className="game-controls-actions">
        <button type="button" onClick={onUndo} className="control-button"><StepBack size={16} />Annuler</button>
        <button type="button" onClick={() => onOrientationChange(orientation === "white" ? "black" : "white")} className="control-button"><FlipHorizontal2 size={16} />Tourner</button>
        <button type="button" onClick={onReset} className="control-button"><RotateCcw size={16} />Reset</button>
        <button type="button" onClick={onCopyFen} className="control-button"><Copy size={16} />FEN</button>
        <button type="button" onClick={onCopyPgn} className="control-button is-wide"><Copy size={16} />Copier PGN</button>
      </div>
    </div>
  );
}
