from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import chess


DATA_DIR = Path(__file__).parents[1] / "data" / "opening_plans"
MAIN_FILES = [
    "beginner_white.json",
    "beginner_black_vs_e4.json",
    "beginner_black_vs_d4.json",
    "beginner_black_flexible.json",
]


def list_available_plans(
    side: str | None = None,
    elo: int | None = None,
    include_hidden: bool = False,
    first_move: str | None = None,
) -> list[dict[str, Any]]:
    plans = [enrich_plan(plan) for plan in load_opening_plans(include_hidden=include_hidden)]
    if side:
        plans = [plan for plan in plans if plan["side"] == side or plan["side"] == "universal"]
    if first_move:
        direct_matching = [
            plan
            for plan in plans
            if first_move in plan.get("against", [])
        ]
        fallback_matching = [
            plan
            for plan in plans
            if "any" in plan.get("against", [])
        ]
        if direct_matching:
            plans = direct_matching
        elif fallback_matching:
            plans = fallback_matching
        elif side == "black":
            plans = [
                plan
                for plan in plans
                if plan.get("tier") in {"recommended", "good"} and plan.get("difficulty") in {"easy", "medium"}
            ]
    if elo is not None:
        plans = [
            plan
            for plan in plans
            if plan.get("recommendedElo", [600, 3200])[0] <= elo <= plan.get("recommendedElo", [600, 3200])[1]
            or plan.get("tier") in {"recommended", "good"}
        ]
    return plans


def get_plan(plan_id: str | None) -> dict[str, Any] | None:
    if not plan_id:
        return None
    plan = next((plan for plan in load_opening_plans(include_hidden=True) if plan["id"] == plan_id), None)
    return enrich_plan(plan) if plan else None


def detect_current_opening(move_history: list[str]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_score = 0
    for plan in load_opening_plans():
        score = _prefix_match_score(move_history, plan.get("mainLineUci", []))
        if score > best_score and score >= 3:
            best = plan
            best_score = score
    return best


def detect_transposition(move_history: list[str]) -> dict[str, Any] | None:
    played = set(move_history)
    best: dict[str, Any] | None = None
    best_overlap = 0
    for plan in load_opening_plans():
        line = set(plan.get("mainLineUci", []))
        overlap = len(played & line)
        if overlap > best_overlap and overlap >= 4:
            best = plan
            best_overlap = overlap
    return best


def get_next_plan_steps(selected_plan_id: str | None, move_history: list[str]) -> list[str]:
    plan = get_plan(selected_plan_id)
    if not plan:
        return []
    line = plan.get("mainLineUci", [])
    if _is_prefix(move_history, line):
        return line[len(move_history) : len(move_history) + 1]
    return _branch_recommendations(plan, move_history)


def get_opponent_deviation(selected_plan_id: str | None, move_history: list[str]) -> dict[str, Any] | None:
    plan = get_plan(selected_plan_id)
    if not plan:
        return None
    line = plan.get("mainLineUci", [])
    for index, played in enumerate(move_history):
        if index >= len(line):
            return {"ply": index + 1, "played": played, "expected": None}
        if played != line[index]:
            return {"ply": index + 1, "played": played, "expected": line[index]}
    return None


def explain_opening_status(plan_state: dict[str, Any]) -> str:
    plan_name = plan_state.get("planName", "ce plan")
    status = plan_state.get("status")
    if status == "on_plan":
        return f"Tu es encore dans {plan_name}. Le prochain objectif est de suivre l'étape indiquée."
    if status == "transposed":
        return f"La position ressemble encore à {plan_name}, mais l'ordre des coups a changé."
    if status == "opponent_deviated":
        return f"L'adversaire a dévié de {plan_name}. On garde les idées générales et on adapte le prochain coup."
    if status == "plan_completed":
        return f"Le plan d'ouverture {plan_name} est terminé. On passe aux objectifs du milieu de jeu."
    return f"Le plan {plan_name} n'est plus une ligne exacte. Utilise les principes de secours."


def suggest_adaptation_after_deviation(fen: str, plan_state: dict[str, Any], stockfish_candidates: list[Any]) -> list[str]:
    if plan_state.get("status") not in {"opponent_deviated", "out_of_book", "transposed"}:
        return []
    return [
        "Vérifier d'abord les menaces directes de l'adversaire.",
        "Garder l'idée principale du plan si elle ne perd pas de matériel.",
        "Développer une pièce ou contester le centre avec un coup sûr.",
    ]


@lru_cache(maxsize=1)
def load_opening_plans(include_hidden: bool = False) -> list[dict[str, Any]]:
    files = MAIN_FILES + (["situational_openings.json", "hidden_traps_lab.json"] if include_hidden else [])
    plans: list[dict[str, Any]] = []
    for filename in files:
        path = DATA_DIR / filename
        if path.exists():
            plans.extend(json.loads(path.read_text(encoding="utf-8")))
    return plans


def enrich_plan(plan: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(plan)
    transition = enriched.get("transitionToMiddlegame", {})
    enriched.setdefault("heroImage", None)
    enriched.setdefault("miniBoardFen", mini_board_fen(enriched.get("mainLineUci", [])))
    enriched.setdefault("shortHistory", short_history_for(enriched))
    enriched.setdefault("learningGoal", enriched.get("beginnerGoal", "Comprendre un plan clair et jouable."))
    enriched.setdefault(
        "successCriteria",
        [
            "La ligne principale ou une branche cohérente a été atteinte.",
            "Le roi est en sécurité ou la sécurité du roi est le prochain objectif.",
            "Les pièces mineures principales sont développées.",
            "Le centre est contesté, clarifié ou stabilisé.",
        ],
    )
    enriched.setdefault("middlegamePlan", transition.get("plans") or default_middlegame_plan(enriched))
    enriched.setdefault(
        "endgamePlan",
        [
            "Activer le roi quand les dames disparaissent.",
            "Créer ou bloquer un pion passé.",
            "Échanger les pièces si cela simplifie un avantage.",
            "Éviter le pat dans les positions gagnantes.",
        ],
    )
    enriched.setdefault("whatYouWillLearn", enriched.get("coreIdeas", [])[:3])
    return enriched


def mini_board_fen(main_line: list[str]) -> str:
    board = chess.Board()
    for move_uci in main_line[:8]:
        try:
            move = chess.Move.from_uci(move_uci)
        except ValueError:
            break
        if move not in board.legal_moves:
            break
        board.push(move)
    return board.fen()


def short_history_for(plan: dict[str, Any]) -> str:
    histories = {
        "caro_kann_beginner": "La Caro-Kann est une reponse solide a 1.e4 : les noirs preparent ...d5 avec ...c6 pour attaquer le centre sans trop affaiblir leur roi.",
        "black_e5_classical": "La defense classique par ...e5 remet un pion au centre tout de suite. Elle enseigne les bases des parties ouvertes : cavaliers actifs, fou developpe et roque rapide.",
        "french_defense_beginner": "La Francaise construit une structure compacte avec ...e6 puis ...d5. Les noirs acceptent parfois moins d'espace pour attaquer la chaine de pions blanche.",
        "scandinavian_simple": "La Scandinave attaque e4 immediatement avec ...d5. Elle est directe, mais demande de developper vite pour ne pas perdre trop de temps avec la dame.",
        "sicilian_dragon_simplified": "La Sicilienne Dragon simplifiee conteste le centre avec ...c5 et place le fou en g7. Elle est active, mais plus exigeante tactiquement.",
        "qgd_simplified": "La defense dame-pion simple repond a 1.d4 par un centre stable. Les noirs tiennent d5, developpent calmement et cherchent un milieu de partie sain.",
        "slav_beginner": "La Slave soutient d5 avec ...c6. Elle garde le centre solide tout en laissant souvent le fou c8 sortir plus librement.",
        "kings_indian_setup": "L'Indienne du roi simplifiee laisse les blancs occuper le centre, puis les noirs roquent vite et preparent une contre-attaque avec ...e5 ou ...c5.",
        "reti_kia_situational": "La Reti et l'Attaque indienne du roi developpent d'abord les pieces, puis choisissent le centre quand la structure adverse est plus claire.",
    }
    if plan.get("id") in histories:
        return histories[str(plan["id"])]
    name = plan.get("nameFr", "Cette ouverture")
    if plan.get("side") == "white":
        return f"{name} donne un plan blanc lisible : prendre ou controler le centre, developper les pieces, puis rejoindre un milieu de partie avec une idee concrete."
    return f"{name} donne aux noirs une reponse organisee : contester le centre blanc, developper les pieces et viser un milieu de partie jouable."


def default_middlegame_plan(plan: dict[str, Any]) -> list[str]:
    ideas = plan.get("coreIdeas", [])[:2]
    return ideas + ["Améliorer la pire pièce.", "Transformer l'ouverture en cible concrète."]


def _prefix_match_score(move_history: list[str], line: list[str]) -> int:
    score = 0
    for played, expected in zip(move_history, line):
        if played != expected:
            break
        score += 1
    return score


def _is_prefix(move_history: list[str], line: list[str]) -> bool:
    return all(index < len(line) and move == line[index] for index, move in enumerate(move_history))


def _branch_recommendations(plan: dict[str, Any], move_history: list[str]) -> list[str]:
    for branch in plan.get("branches", []):
        trigger = branch.get("triggerLineUci", [])
        if _is_prefix(trigger, move_history) or _is_prefix(move_history, trigger):
            return branch.get("recommendedMoves", [])[:3]
    return []
