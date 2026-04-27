from __future__ import annotations

import re
from typing import Any


UCI_SEQUENCE_RE = re.compile(r"\b[a-h][1-8][a-h][1-8][qrbn]?(?:\s+[a-h][1-8][a-h][1-8][qrbn]?)+\b")
SQUARE_RE = re.compile(r"\b[a-h][1-8]\b")


def verify_explanation(payload: dict[str, Any], expected_piece: str, active_plan_name: str | None = None) -> dict[str, Any]:
    text = _flatten({key: value for key, value in payload.items() if key != "technical"})
    problems = []
    if expected_piece and expected_piece not in text:
        problems.append("missing_expected_piece")
    if UCI_SEQUENCE_RE.search(text):
        problems.append("raw_uci_sequence")
    if " cp" in text.lower():
        problems.append("cp_in_beginner_mode")
    if not SQUARE_RE.search(text):
        problems.append("no_square")
    if active_plan_name and active_plan_name not in text:
        problems.append("missing_active_plan")
    if "nextSteps" in payload and not payload.get("nextSteps"):
        problems.append("missing_next_step")

    grounding = max(0.0, 1.0 - len(problems) * 0.18)
    clarity = max(0.0, 1.0 - len([p for p in problems if p in {"raw_uci_sequence", "cp_in_beginner_mode"}]) * 0.3)
    return {
        "isValid": grounding >= 0.75 and not problems,
        "groundingScore": round(grounding, 2),
        "beginnerClarityScore": round(clarity, 2),
        "problems": problems,
    }


def _flatten(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_flatten(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_flatten(item) for item in value.values())
    return str(value)
