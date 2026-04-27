from __future__ import annotations

from typing import Any

from ..explanations.explanation_verifier import verify_explanation


def verify_with_optional_provider(payload: dict[str, Any], expected_piece: str, active_plan_name: str | None = None) -> dict[str, Any]:
    return verify_explanation(payload, expected_piece, active_plan_name)
