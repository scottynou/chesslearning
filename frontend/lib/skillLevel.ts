import type { SkillLevel } from "./types";

export const SKILL_LEVELS: Array<{
  id: SkillLevel;
  label: string;
  elo: number;
  engineDepth: number;
  maxMoves: number;
  description: string;
}> = [
  {
    id: "beginner",
    label: "Débutant",
    elo: 1200,
    engineDepth: 8,
    maxMoves: 3,
    description: "Un coup clair, peu d'alternatives, vocabulaire simple."
  },
  {
    id: "intermediate",
    label: "Intermédiaire",
    elo: 1900,
    engineDepth: 10,
    maxMoves: 4,
    description: "Plus d'adaptations et un peu plus de stratégie."
  },
  {
    id: "pro",
    label: "Pro",
    elo: 2800,
    engineDepth: 12,
    maxMoves: 5,
    description: "Stockfish pèse davantage et les alternatives sont plus précises."
  }
];

export function skillSettings(level: SkillLevel) {
  return SKILL_LEVELS.find((item) => item.id === level) ?? SKILL_LEVELS[0];
}
