from __future__ import annotations

from typing import Any

from .base import AiProvider


class HeuristicProvider(AiProvider):
    def explain_candidate(self, context: dict[str, Any], timeout_seconds: float = 0) -> dict[str, Any]:
        selected = context["selectedMove"]
        piece = selected["pieceName"]
        from_square = selected["from"]
        to_square = selected["to"]
        move_label = selected["beginnerLabel"]
        eval_label = selected["evalLabel"]
        pv = context.get("translatedPv", [])
        first_reply = pv[1] if len(pv) > 1 else None
        next_plan = _plan_for(piece, to_square, context)

        reply_sentence = (
            f"L'adversaire peut répondre par {first_reply['beginnerLabel']} : {first_reply['simpleExplanation']}"
            if first_reply
            else f"L'adversaire doit surtout surveiller la case {to_square} et les cases centrales."
        )

        return {
            "title": _title_for(piece, to_square),
            "moveLabel": move_label,
            "oneSentence": f"Ce coup joue {piece} de {from_square} vers {to_square} pour améliorer la position et viser le centre.",
            "sections": {
                "whatToDo": f"Joue {move_label}.",
                "mainIdea": _main_idea(piece, from_square, to_square),
                "whyNow": _why_now(piece, context),
                "whatItProvokes": reply_sentence,
                "nextPlan": next_plan,
                "danger": _danger(piece, to_square),
                "commonMistake": f"Un débutant joue parfois {piece} vers {to_square}, puis oublie le plan et déplace encore la même pièce sans raison.",
                "betterThan": _better_than(context, eval_label),
            },
            "technical": {
                "san": selected["san"],
                "uci": selected["uci"],
                "evalCp": context["selectedMoveRaw"].get("evalCp"),
                "pv": context["selectedMoveRaw"].get("pv", []),
            },
            "translatedPv": pv,
        }


def _title_for(piece: str, to_square: str) -> str:
    if piece == "Cavalier":
        return f"Sortir le cavalier vers {to_square} et contrôler le centre"
    if piece == "Pion" and to_square in {"d4", "e4", "d5", "e5", "c4", "c5"}:
        return f"Utiliser le pion en {to_square} pour lutter au centre"
    if piece == "Fou":
        return f"Activer le fou vers {to_square}"
    if piece == "Roi":
        return "Mettre le roi en sécurité"
    return f"Améliorer la pièce vers {to_square}"


def _main_idea(piece: str, from_square: str, to_square: str) -> str:
    if piece == "Cavalier":
        return f"Le Cavalier quitte {from_square} pour aller en {to_square}. Depuis cette case, il se rapproche des cases centrales e4, d5, e5 et d4."
    if piece == "Pion":
        return f"Le Pion avance de {from_square} à {to_square}. Il aide à prendre de l'espace ou à attaquer un pion central adverse."
    if piece == "Fou":
        return f"Le Fou quitte {from_square} pour aller en {to_square}. Il ouvre une diagonale et participe plus vite au jeu."
    if piece == "Roi":
        return f"Le Roi bouge de {from_square} à {to_square}. Le but principal est sa sécurité."
    return f"La pièce {piece} passe de {from_square} à {to_square} pour devenir plus active."


def _why_now(piece: str, context: dict[str, Any]) -> str:
    center = context.get("positionContext", {}).get("centerPawns", "")
    if piece in {"Cavalier", "Fou"}:
        return f"C'est utile maintenant car les pièces mineures doivent sortir tôt. {center}"
    if piece == "Pion":
        return f"C'est utile maintenant parce que la bataille se joue autour des cases centrales. {center}"
    return "C'est utile maintenant si la pièce gagne une case active sans créer de faiblesse immédiate."


def _danger(piece: str, to_square: str) -> str:
    if piece == "Cavalier":
        return f"Ne bouge pas le Cavalier en {to_square} une deuxième fois sans menace concrète : développe aussi les autres pièces."
    if piece == "Pion":
        return f"Après avoir avancé le Pion en {to_square}, vérifie que les cases derrière lui ne deviennent pas faibles."
    return f"Vérifie que la pièce en {to_square} n'est pas attaquée gratuitement."


def _plan_for(piece: str, to_square: str, context: dict[str, Any]) -> list[str]:
    if piece == "Cavalier":
        return [
            f"Mettre le Cavalier en {to_square}.",
            "Attaquer ou défendre les cases centrales e4 et d5.",
            "Développer l'autre Cavalier ou un Fou.",
            "Préparer le roque.",
        ]
    if piece == "Pion":
        return [
            f"Installer le Pion en {to_square}.",
            "Développer un Cavalier vers le centre.",
            "Sortir un Fou.",
            "Mettre le roi en sécurité.",
        ]
    return context.get("positionContext", {}).get("phasePlan", []) or [
        f"Jouer la pièce vers {to_square}.",
        "Vérifier les menaces adverses.",
        "Développer une autre pièce.",
    ]


def _better_than(context: dict[str, Any], eval_label: str) -> str:
    alternatives = context.get("topAlternatives", [])
    if alternatives:
        best = alternatives[0]
        return (
            f"Comparé à {best['beginnerLabel']}, ce coup garde une idée claire pour ce niveau. "
            f"L'évaluation indique : {eval_label}."
        )
    return f"Ce coup est choisi parce qu'il reste compréhensible et que l'évaluation indique : {eval_label}."
