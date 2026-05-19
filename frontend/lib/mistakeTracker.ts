import { loadGames, type SavedGame } from "./gameHistory";

export type MistakeCategory = "blunder" | "mistake" | "inaccurate";
export type MistakePhase = "opening" | "middlegame" | "endgame";

export type MistakePattern = {
  category: MistakeCategory;
  phase: MistakePhase;
  count: number;
  averageLoss: number;
  examples: Array<{ gameId: string; ply: number; san?: string; loss: number }>;
};

export type MistakeReport = {
  totalGames: number;
  patterns: MistakePattern[];
  worstCategory: MistakeCategory | null;
  weakestPhase: MistakePhase | null;
  suggestion: string;
};

export function buildMistakeReport(games: SavedGame[] = loadGames(), recentLimit = 20): MistakeReport {
  const recent = games.slice(0, recentLimit);
  const buckets = new Map<string, MistakePattern>();

  for (const game of recent) {
    for (const sample of game.summary.samples) {
      if (sample.quality !== "blunder" && sample.quality !== "mistake" && sample.quality !== "inaccurate") continue;
      const phase = inferPhase(sample.ply, game.summary.samples.length);
      const key = `${sample.quality}|${phase}`;
      const existing = buckets.get(key) ?? {
        category: sample.quality as MistakeCategory,
        phase,
        count: 0,
        averageLoss: 0,
        examples: []
      };
      existing.count += 1;
      existing.averageLoss = (existing.averageLoss * (existing.count - 1) + sample.centipawnLoss) / existing.count;
      if (existing.examples.length < 3) {
        existing.examples.push({ gameId: game.id, ply: sample.ply, san: sample.san, loss: sample.centipawnLoss });
      }
      buckets.set(key, existing);
    }
  }

  const patterns = Array.from(buckets.values()).sort((a, b) => weight(b) - weight(a));
  const worstCategory = patterns[0]?.category ?? null;
  const weakestPhase = patterns[0]?.phase ?? null;

  return {
    totalGames: recent.length,
    patterns,
    worstCategory,
    weakestPhase,
    suggestion: buildSuggestion(patterns, recent.length)
  };
}

function weight(pattern: MistakePattern): number {
  const severity = pattern.category === "blunder" ? 3 : pattern.category === "mistake" ? 2 : 1;
  return pattern.count * severity + pattern.averageLoss / 25;
}

function inferPhase(ply: number, totalSamples: number): MistakePhase {
  if (ply <= 20) return "opening";
  if (totalSamples > 0 && ply > totalSamples * 0.7 + 20) return "endgame";
  return "middlegame";
}

function buildSuggestion(patterns: MistakePattern[], games: number): string {
  if (games === 0) return "Joue quelques parties pour voir tes patterns d'erreurs.";
  if (patterns.length === 0) return "Aucune erreur recurrente sur tes dernieres parties. Continue ainsi.";
  const top = patterns[0];
  const categoryText = top.category === "blunder" ? "gaffes" : top.category === "mistake" ? "erreurs" : "imprecisions";
  const phaseText = top.phase === "opening" ? "en ouverture" : top.phase === "middlegame" ? "en milieu de jeu" : "en finale";
  return `Tu fais surtout des ${categoryText} ${phaseText} (${top.count} cas sur ${games} parties). Entraine-toi sur cette phase.`;
}
