export type PuzzleTheme =
  | "fork"
  | "pin"
  | "skewer"
  | "discovered"
  | "back_rank"
  | "mate_in_1"
  | "mate_in_2"
  | "deflection";

export type Puzzle = {
  id: string;
  theme: PuzzleTheme;
  themeLabel: string;
  difficulty: 1 | 2 | 3;
  fen: string;
  /** Le coup gagnant en notation UCI (ex: "e2e4"). */
  bestMoveUci: string;
  /** Description du theme + indice avant resolution. */
  hint: string;
  /** Explication post-resolution. */
  explanation: string;
};

const THEME_LABELS: Record<PuzzleTheme, string> = {
  fork: "Fourchette",
  pin: "Clouage",
  skewer: "Enfilade",
  discovered: "Attaque a la decouverte",
  back_rank: "Mat du couloir",
  mate_in_1: "Mat en 1",
  mate_in_2: "Mat en 2",
  deflection: "Deflexion"
};

function puzzle(
  id: string,
  theme: PuzzleTheme,
  difficulty: 1 | 2 | 3,
  fen: string,
  bestMoveUci: string,
  hint: string,
  explanation: string
): Puzzle {
  return {
    id,
    theme,
    themeLabel: THEME_LABELS[theme],
    difficulty,
    fen,
    bestMoveUci,
    hint,
    explanation
  };
}

export const PUZZLES: Puzzle[] = [
  // ===== Mat en 1 =====
  puzzle(
    "m1-001",
    "mate_in_1",
    1,
    "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1",
    "d1d8",
    "Le roi noir est seul sur la 8e rangee, sans defense.",
    "Td8# : la tour entre sur la 8e rangee, le roi noir n'a pas de case d'evasion (g7/g8/f8 controles)."
  ),
  puzzle(
    "m1-002",
    "mate_in_1",
    1,
    "6k1/6pp/8/8/8/8/5PPP/4R1K1 w - - 0 1",
    "e1e8",
    "Tour libre sur la colonne e, roi adverse coince.",
    "Te8# : echec du couloir, h7/g7 bloques par les pions noirs."
  ),
  puzzle(
    "m1-003",
    "mate_in_1",
    1,
    "r6k/6pp/8/8/8/8/6PP/6KR w - - 0 1",
    "h1h8",
    "Tour qui prend la colonne ouverte avec un mat du couloir.",
    "Txh8# : la tour mate directement, le roi noir est etouffe."
  ),

  // ===== Fourchette de cavalier =====
  puzzle(
    "fork-001",
    "fork",
    1,
    "r3k2r/ppp2ppp/2n5/3qp3/4P3/2N5/PPP2PPP/R2QKB1R w KQkq - 0 1",
    "c3d5",
    "Le cavalier peut attaquer dame et roi en meme temps.",
    "Cxd5 : fourchette royale ! Le cavalier attaque la dame noire et donne echec via la tour. La dame tombe."
  ),
  puzzle(
    "fork-002",
    "fork",
    2,
    "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 4 5",
    "c4f7",
    "Le coup classique sur f7. Le roi est encore au centre.",
    "Bxf7+ : echec au roi, et le cavalier en c6 ou la dame en d8 tombent souvent au coup suivant."
  ),
  puzzle(
    "fork-003",
    "fork",
    2,
    "r2qkb1r/ppp2ppp/2n5/3np1B1/4P3/2N5/PPP2PPP/R2QKB1R w KQkq - 0 1",
    "c3d5",
    "Une fourchette sur la dame et le cavalier mal places.",
    "Cxd5 : la dame doit fuir et on gagne ensuite le cavalier en d5."
  ),

  // ===== Clouage =====
  puzzle(
    "pin-001",
    "pin",
    1,
    "r1bqk2r/pppp1ppp/2n2n2/4p3/1bB1P3/2NP1N2/PPP2PPP/R1BQK2R w KQkq - 4 6",
    "c1g5",
    "Le cavalier f6 est cloue contre la dame.",
    "Bg5 : le cavalier noir ne peut plus bouger (sinon la dame tombe). On peut le capturer en doublant l'attaque."
  ),
  puzzle(
    "pin-002",
    "pin",
    2,
    "rn1qkb1r/ppp2ppp/3p1n2/4p1B1/3PP1b1/2N2N2/PPP2PPP/R2QKB1R w KQkq - 0 1",
    "d4e5",
    "Casser le centre pour ouvrir le clouage du fou g4.",
    "dxe5 : le pion d6 noir est cloue, le fou g4 va perdre l'echange."
  ),

  // ===== Enfilade =====
  puzzle(
    "skewer-001",
    "skewer",
    1,
    "4k3/8/8/8/8/8/4R3/4K1q1 w - - 0 1",
    "e2e8",
    "Le roi et la dame noirs alignes sur la colonne e.",
    "Te8+ : echec, le roi doit bouger et on capture la dame derriere."
  ),
  puzzle(
    "skewer-002",
    "skewer",
    2,
    "8/3k4/8/8/3R4/8/8/3qK3 w - - 0 1",
    "d4d1",
    "Echec a la decouverte qui enfile la dame.",
    "Txd1+ : echec, capture la dame, partie gagnante."
  ),

  // ===== Attaque a la decouverte =====
  puzzle(
    "disc-001",
    "discovered",
    2,
    "r3kbnr/ppp1pppp/2n5/1B1q4/3P4/2N2N2/PPP2PPP/R1BQK2R w KQkq - 0 1",
    "b5c6",
    "Le fou en b5 deplace decouvre la dame sur la dame noire.",
    "Bxc6+ : echec a la decouverte par la dame ! On gagne la dame ou du materiel."
  ),

  // ===== Mat du couloir =====
  puzzle(
    "back-001",
    "back_rank",
    1,
    "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1",
    "a1a8",
    "Mat du couloir classique.",
    "Ta8# : la tour entre, le roi est etouffe par ses propres pions."
  ),
  puzzle(
    "back-002",
    "back_rank",
    2,
    "3r2k1/5ppp/8/8/8/8/5PPP/R3R1K1 w - - 0 1",
    "e1e8",
    "Echange de tours, puis mat du couloir.",
    "Txe8+ Txe8 Txe8# : sequence force pour le mat."
  ),

  // ===== Deflexion =====
  puzzle(
    "defl-001",
    "deflection",
    2,
    "r1bq1rk1/ppp2ppp/2n5/3pp3/3P4/2P1P3/PP3PPP/RNBQ1RK1 w - - 0 1",
    "d4e5",
    "Casser le centre pour ouvrir des lignes contre le roi.",
    "dxe5 : la dame defend mal sa propre case e5. La capture ouvre la colonne d."
  ),

  // ===== Mat en 2 =====
  puzzle(
    "m2-001",
    "mate_in_2",
    3,
    "r1bq1rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/3P1N2/PPP1QPPP/RNB2RK1 w - - 0 1",
    "e2e3",
    "Prepare le mat en 2 via une menace sur le roi.",
    "Qe3 puis Bxf7+ Rxf7 Qxe5 : sequence avec gain de materiel decisif."
  ),

  // ===== Fourchette de dame =====
  puzzle(
    "fork-004",
    "fork",
    2,
    "r2q1rk1/ppp2ppp/2np1n2/2b1p1B1/2B1P3/2NP1N2/PPP1QPPP/R4RK1 w - - 0 1",
    "g5f6",
    "Capture qui ouvre une fourchette de dame.",
    "Bxf6 gxf6 puis Qg4+ recupere la piece et capitalise."
  ),

  // ===== Clouage tactique =====
  puzzle(
    "pin-003",
    "pin",
    2,
    "rnbqkbnr/ppp1pppp/8/3p4/3P4/2N5/PPP1PPPP/R1BQKBNR b KQkq - 1 2",
    "c8g4",
    "Cloue le cavalier qui defend e4 d4.",
    "Bg4 : le cavalier en c3 sera bientot mis sous pression, cloue contre la dame."
  )
];

export function puzzlesByTheme(theme?: PuzzleTheme): Puzzle[] {
  if (!theme) return PUZZLES;
  return PUZZLES.filter((p) => p.theme === theme);
}

export function shuffledPuzzles(): Puzzle[] {
  const arr = [...PUZZLES];
  for (let i = arr.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

export const ALL_THEMES: PuzzleTheme[] = [
  "mate_in_1",
  "mate_in_2",
  "fork",
  "pin",
  "skewer",
  "discovered",
  "back_rank",
  "deflection"
];

export function labelForTheme(theme: PuzzleTheme): string {
  return THEME_LABELS[theme];
}
