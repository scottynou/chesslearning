from __future__ import annotations


def evaluation_label(eval_cp: int | None, mate_in: int | None = None) -> str:
    if mate_in is not None:
        return f"Mat en {abs(mate_in)}"
    if eval_cp is None:
        return "Évaluation inconnue"

    absolute = abs(eval_cp)
    if absolute < 30:
        return "Position équilibrée"

    side = "blanc" if eval_cp > 0 else "noir"
    if absolute < 80:
        return f"Léger avantage {side}"
    if absolute < 150:
        return f"Avantage clair {side}"
    if absolute < 300:
        return f"Gros avantage {side}"
    return f"Avantage décisif {side}"


def raw_eval_label(eval_cp: int | None, mate_in: int | None = None) -> str:
    if mate_in is not None:
        return f"mate {mate_in}"
    if eval_cp is None:
        return "n/a"
    return f"{eval_cp} cp"
