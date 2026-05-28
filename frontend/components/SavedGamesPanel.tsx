"use client";

import { useEffect, useState } from "react";

import { deleteGame, loadGames, type SavedGame } from "@/lib/gameHistory";
import { PostGameReview } from "./PostGameReview";

type Props = {
  onClose?: () => void;
};

export function SavedGamesPanel({ onClose }: Props) {
  const [games, setGames] = useState<SavedGame[]>([]);
  const [selected, setSelected] = useState<SavedGame | null>(null);

  useEffect(() => {
    setGames(loadGames());
  }, []);

  function handleDelete(id: string) {
    const next = deleteGame(id);
    setGames(next);
    if (selected?.id === id) setSelected(null);
  }

  if (selected) {
    return (
      <div className="saved-games-panel">
        <button type="button" className="saved-games-back" onClick={() => setSelected(null)}>
          ← Retour à la liste
        </button>
        <PostGameReview summary={selected.summary} resultText={selected.result} />
      </div>
    );
  }

  return (
    <div className="saved-games-panel">
      <header className="saved-games-header">
        <h3>Mes parties</h3>
        {onClose ? (
          <button type="button" className="saved-games-close" onClick={onClose} aria-label="Fermer">
            ✕
          </button>
        ) : null}
      </header>
      {games.length === 0 ? (
        <p className="saved-games-empty">Aucune partie sauvegardée pour l&apos;instant.</p>
      ) : (
        <ul className="saved-games-list">
          {games.map((game) => (
            <li key={game.id} className="saved-games-item">
              <button type="button" className="saved-games-item-main" onClick={() => setSelected(game)}>
                <span className="saved-games-item-date">{formatDate(game.savedAt)}</span>
                <span className="saved-games-item-meta">
                  {game.userSide === "white" ? "Blancs" : game.userSide === "black" ? "Noirs" : "Libre"} ·{" "}
                  {profileLabel(game.humanProfile)} · {styleLabel(game.coachStyle)}
                </span>
                <span className="saved-games-item-result">{game.result}</span>
                <span className="saved-games-item-accuracy">
                  {game.summary.weightedAccuracy.toFixed(1)}%
                </span>
              </button>
              <button
                type="button"
                className="saved-games-item-delete"
                onClick={() => handleDelete(game.id)}
                aria-label="Supprimer cette partie"
              >
                Supprimer
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function formatDate(timestamp: number): string {
  try {
    return new Date(timestamp).toLocaleString("fr-FR", {
      day: "2-digit",
      month: "2-digit",
      year: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
  } catch {
    return new Date(timestamp).toISOString();
  }
}

function profileLabel(profile: string): string {
  if (profile === "beginner") return "800";
  if (profile === "lambda") return "1500";
  if (profile === "strong") return "2000";
  if (profile === "veryStrong") return "3000";
  return profile;
}

function styleLabel(style: string): string {
  const map: Record<string, string> = {
    balanced: "Equilibre",
    aggressive: "Agressif",
    solid: "Solide",
    creative: "Creatif",
    educational: "Pedago"
  };
  return map[style] ?? style;
}
