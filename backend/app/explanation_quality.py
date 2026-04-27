from __future__ import annotations

import re
from typing import Any


UCI_SEQUENCE_RE = re.compile(r"\b[a-h][1-8][a-h][1-8][qrbn]?(?:\s+[a-h][1-8][a-h][1-8][qrbn]?)+\b")
SINGLE_UCI_RE = re.compile(r"\b[a-h][1-8][a-h][1-8][qrbn]?\b")
SQUARE_RE = re.compile(r"\b[a-h][1-8]\b")
PIECE_NAMES = {"Pion", "Cavalier", "Fou", "Tour", "Dame", "Roi"}
GENERIC_PATTERNS = [
    re.compile(r"continue le développement(?!.*\b(Pion|Cavalier|Fou|Tour|Dame|Roi)\b)", re.IGNORECASE),
    re.compile(r"réponse naturelle(?!.*\b[a-h][1-8]\b)", re.IGNORECASE),
    re.compile(r"variante moteur commence", re.IGNORECASE),
]


class ExplanationQualityError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def assert_beginner_explanation_quality(payload: dict[str, Any], piece_name: str) -> None:
    public_payload = {key: value for key, value in payload.items() if key != "technical"}
    text = _flatten_text(public_payload)
    errors = validate_beginner_explanation(text, piece_name)
    if errors:
        raise ExplanationQualityError(errors)


def validate_beginner_explanation(text: str, piece_name: str) -> list[str]:
    errors: list[str] = []
    if UCI_SEQUENCE_RE.search(text):
        errors.append("contains_raw_uci_sequence")
    if " cp" in text.lower() or "centipion" in text.lower():
        errors.append("contains_cp")
    for pattern in GENERIC_PATTERNS:
        if pattern.search(text):
            errors.append("contains_generic_phrase")
    if not SQUARE_RE.search(text):
        errors.append("contains_no_square")
    if piece_name and piece_name not in text:
        errors.append("missing_played_piece_name")
    if not any(piece in text for piece in PIECE_NAMES):
        errors.append("contains_no_piece_name")
    return errors


def _flatten_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        return " ".join(_flatten_text(value) for value in payload.values())
    if isinstance(payload, list):
        return " ".join(_flatten_text(value) for value in payload)
    return str(payload)
