import type { StrategyPlan } from "@/lib/types";

const OPENING_VISUALS: Record<string, string> = {
  alekhine_defense_learning: "./openings/alekhine_defense_learning.svg",
  benoni_learning: "./openings/benoni_learning.svg",
  black_e5_classical: "./openings/black_e5_classical.svg",
  black_e6_flexible: "./openings/black_e6_flexible.svg",
  black_fianchetto_universal: "./openings/black_fianchetto_universal.svg",
  black_flexible_d5_classical: "./openings/black_flexible_d5_classical.svg",
  caro_kann_beginner: "./openings/caro_kann_beginner.svg",
  catalan_simplified: "./openings/catalan_simplified.svg",
  colle_system_beginner: "./openings/colle_system_beginner.svg",
  dutch_defense_learning: "./openings/dutch_defense_learning.svg",
  english_e5_response: "./openings/english_e5_response.svg",
  english_opening_practical: "./openings/english_opening_practical.svg",
  englund_trap_lab: "./openings/englund_trap_lab.svg",
  four_knights_beginner: "./openings/four_knights_beginner.svg",
  french_defense_beginner: "./openings/french_defense_beginner.svg",
  grunfeld_simplified: "./openings/grunfeld_simplified.svg",
  italian_game_beginner: "./openings/italian_game_beginner.svg",
  kings_indian_setup: "./openings/kings_indian_setup.svg",
  london_system_beginner: "./openings/london_system_beginner.svg",
  modern_defense_learning: "./openings/modern_defense_learning.svg",
  nimzo_indian_simplified: "./openings/nimzo_indian_simplified.svg",
  petroff_defense_learning: "./openings/petroff_defense_learning.svg",
  philidor_defense_learning: "./openings/philidor_defense_learning.svg",
  pirc_defense_learning: "./openings/pirc_defense_learning.svg",
  qgd_simplified: "./openings/qgd_simplified.svg",
  queens_gambit_beginner: "./openings/queens_gambit_beginner.svg",
  queens_indian_simplified: "./openings/queens_indian_simplified.svg",
  reti_kia_practical: "./openings/reti_kia_practical.svg",
  reti_kia_situational: "./openings/reti_kia_situational.svg",
  ruy_lopez_simplified: "./openings/ruy_lopez_simplified.svg",
  scandinavian_simple: "./openings/scandinavian_simple.svg",
  scotch_game_beginner: "./openings/scotch_game_beginner.svg",
  sicilian_dragon_simplified: "./openings/sicilian_dragon_simplified.svg",
  sicilian_najdorf_learning: "./openings/sicilian_najdorf_learning.svg",
  slav_beginner: "./openings/slav_beginner.svg",
  symmetrical_english_response: "./openings/symmetrical_english_response.svg",
  tarrasch_defense_learning: "./openings/tarrasch_defense_learning.svg",
  vienna_game_practical: "./openings/vienna_game_practical.svg"
};

export function getOpeningImageSrc(plan: StrategyPlan) {
  return plan.heroImage || OPENING_VISUALS[plan.id] || "./openings/generic_opening.svg";
}
