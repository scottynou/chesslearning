from __future__ import annotations

from .schemas import ExplainRequest, ExplainResponse


def explain_heuristically(request: ExplainRequest) -> ExplainResponse:
    move = request.selected_move
    best = min(request.all_candidates, key=lambda candidate: candidate.stockfish_rank, default=move)
    is_best = move.move_uci == best.move_uci

    title = _title_for(move.move_san, move.summary)
    comparison = (
        "Ce coup correspond aussi au premier choix Stockfish dans les lignes reçues."
        if is_best
        else (
            f"Stockfish préfère {best.move_san}, mais {move.move_san} peut être plus adapté "
            f"pédagogiquement à {request.elo} Elo grâce à son équilibre entre clarté, risque et valeur moteur."
        )
    )

    return ExplainResponse(
        moveSan=move.move_san,
        title=title,
        explanation={
            "mainIdea": (
                f"L'idée principale de {move.move_san} est la suivante : {move.summary} "
                f"La variante moteur commence par {_format_pv(move.pv)}."
            ),
            "whyForThisElo": (
                f"À {request.elo} Elo, ce coup reçoit un score coach de {move.coach_score}/100. "
                f"Il combine valeur moteur ({move.engine_score}/100), simplicité ({move.simplicity_score}/100) "
                f"et risque {move.risk}."
            ),
            "expectedOpponentReaction": (
                "La réaction adverse la plus probable est de répondre au plan direct indiqué par la variante. "
                f"Dans les données moteur reçues, la suite commence par {_format_reply(move.pv)}."
            ),
            "planA": (
                "Si l'adversaire suit une réponse naturelle, continue le développement, protège les pièces "
                "engagées et vérifie que le centre reste stable avant de chercher une tactique."
            ),
            "planB": (
                "Si l'adversaire défend autrement, reprends la position calmement : cherche d'abord les menaces "
                "sur ton roi, puis les captures gratuites, puis l'amélioration de ta pire pièce."
            ),
            "whatToWatch": (
                "Surveille les pièces non défendues, les échecs intermédiaires et les captures qui changent "
                "brutalement l'évaluation."
            ),
            "commonMistake": (
                "L'erreur fréquente est de jouer le premier coup du plan puis d'oublier pourquoi il a été joué. "
                "Après la réponse adverse, il faut réévaluer la menace principale."
            ),
            "comparison": comparison,
        },
    )


def _title_for(move_san: str, summary: str) -> str:
    if "centre" in summary or "espace" in summary:
        return f"{move_san} : prendre le centre simplement"
    if "Développe" in summary:
        return f"{move_san} : développer avec un plan clair"
    if "roi" in summary:
        return f"{move_san} : sécuriser le roi"
    if "matériel" in summary:
        return f"{move_san} : concrétiser le matériel"
    return f"{move_san} : améliorer la position"


def _format_pv(pv: list[str]) -> str:
    if not pv:
        return "aucune suite principale n'a été fournie"
    return " ".join(pv[:5])


def _format_reply(pv: list[str]) -> str:
    if len(pv) < 2:
        return "aucune réponse adverse précise n'a été fournie"
    return pv[1]
