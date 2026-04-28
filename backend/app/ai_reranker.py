from __future__ import annotations

import json
import os
from time import monotonic
from typing import Any

import httpx


RERANK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "orderedMoveUci": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": ["orderedMoveUci", "confidence"],
}


def rerank_recommendations(
    *,
    fen: str,
    selected_plan: dict[str, Any] | None,
    phase: str,
    opening_state: str,
    move_history: list[str],
    recommendations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(recommendations) <= 1:
        return recommendations, _status("disabled", fallback_reason="single_or_empty_candidate_list")

    provider = os.getenv("AI_RERANK_PROVIDER", "gemini").lower().strip()
    if provider in {"none", "off", "disabled"}:
        return recommendations, _status("disabled", provider=provider, fallback_reason="disabled_by_env")

    timeout_seconds = _float_env("AI_RERANK_TIMEOUT_SECONDS", 0.7)
    started = monotonic()
    try:
        if provider == "gemini":
            ordered = _gemini_rerank(
                fen=fen,
                selected_plan=selected_plan,
                phase=phase,
                opening_state=opening_state,
                move_history=move_history,
                recommendations=recommendations,
                timeout_seconds=timeout_seconds,
            )
            return _apply_order(recommendations, ordered), _status(
                "success",
                provider="gemini",
                model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite"),
                latency_ms=_elapsed_ms(started),
            )

        if provider in {"openai-compatible", "openrouter", "groq", "openai"}:
            ordered = _openai_compatible_rerank(
                provider=provider,
                fen=fen,
                selected_plan=selected_plan,
                phase=phase,
                opening_state=opening_state,
                move_history=move_history,
                recommendations=recommendations,
                timeout_seconds=timeout_seconds,
            )
            return _apply_order(recommendations, ordered), _status(
                "success",
                provider=provider,
                model=os.getenv("AI_RERANK_MODEL", ""),
                latency_ms=_elapsed_ms(started),
            )

        return recommendations, _status(
            "fallback",
            provider=provider,
            fallback_reason=f"unsupported_provider:{provider}",
            latency_ms=_elapsed_ms(started),
        )
    except Exception as exc:
        return recommendations, _status(
            "fallback",
            provider=provider,
            model=_model_for_provider(provider),
            fallback_reason=type(exc).__name__,
            latency_ms=_elapsed_ms(started),
        )


def _gemini_rerank(
    *,
    fen: str,
    selected_plan: dict[str, Any] | None,
    phase: str,
    opening_state: str,
    move_history: list[str],
    recommendations: list[dict[str, Any]],
    timeout_seconds: float,
) -> list[str]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("missing_gemini_key")

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    response = httpx.post(
        url,
        headers={"x-goog-api-key": api_key},
        json={
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": _prompt(fen, selected_plan, phase, opening_state, move_history, recommendations)}],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": RERANK_SCHEMA,
            },
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return _ordered_moves_from_payload(json.loads(text))


def _openai_compatible_rerank(
    *,
    provider: str,
    fen: str,
    selected_plan: dict[str, Any] | None,
    phase: str,
    opening_state: str,
    move_history: list[str],
    recommendations: list[dict[str, Any]],
    timeout_seconds: float,
) -> list[str]:
    api_key = os.getenv("AI_RERANK_API_KEY")
    model = os.getenv("AI_RERANK_MODEL")
    if not api_key:
        raise RuntimeError("missing_ai_rerank_api_key")
    if not model:
        raise RuntimeError("missing_ai_rerank_model")

    base_url = os.getenv("AI_RERANK_BASE_URL") or _default_base_url(provider)
    if not base_url:
        raise RuntimeError("missing_ai_rerank_base_url")
    url = base_url.rstrip("/") + "/chat/completions"

    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a hidden chess move reranker. Return strict JSON only.",
                },
                {
                    "role": "user",
                    "content": _prompt(fen, selected_plan, phase, opening_state, move_history, recommendations),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return _ordered_moves_from_payload(json.loads(content))


def _prompt(
    fen: str,
    selected_plan: dict[str, Any] | None,
    phase: str,
    opening_state: str,
    move_history: list[str],
    recommendations: list[dict[str, Any]],
) -> str:
    compact_candidates = [
        {
            "moveUci": item.get("moveUci"),
            "moveSan": item.get("moveSan"),
            "displayRole": item.get("displayRole"),
            "source": item.get("source"),
            "engineRank": item.get("engineRank"),
            "planRank": item.get("planRank"),
            "planFitScore": item.get("planFitScore"),
            "engineScore": item.get("engineScore"),
            "beginnerSimplicityScore": item.get("beginnerSimplicityScore"),
            "tacticalRisk": item.get("tacticalRisk"),
            "finalCoachScore": item.get("finalCoachScore"),
            "humanAccuracyEstimate": item.get("humanAccuracyEstimate"),
            "accuracyBand": item.get("accuracyBand"),
            "warning": item.get("warning"),
        }
        for item in recommendations
    ]
    payload = {
        "task": (
            "Rank only these legal candidate moves. Do not invent a move. Prefer the selected opening plan when safe, "
            "then engine safety, then human simplicity around 1200 Elo. In stable positions, prefer the hidden "
            "humanAccuracyEstimate band over always choosing the top engine move. In pressure or survival positions, "
            "prioritize the strongest safe move."
        ),
        "output": {"orderedMoveUci": ["only candidate moveUci values in best order"], "confidence": "0-100"},
        "fen": fen,
        "phase": phase,
        "openingState": opening_state,
        "selectedPlan": {
            "id": selected_plan.get("id"),
            "nameFr": selected_plan.get("nameFr"),
            "side": selected_plan.get("side"),
            "coreIdeas": selected_plan.get("coreIdeas", [])[:4],
        }
        if selected_plan
        else None,
        "moveHistoryUci": move_history[-12:],
        "candidates": compact_candidates,
    }
    return json.dumps(payload, ensure_ascii=True)


def _ordered_moves_from_payload(payload: dict[str, Any]) -> list[str]:
    ordered = payload.get("orderedMoveUci")
    if not isinstance(ordered, list):
        raise RuntimeError("invalid_rerank_payload")
    return [move for move in ordered if isinstance(move, str)]


def _apply_order(recommendations: list[dict[str, Any]], ordered_moves: list[str]) -> list[dict[str, Any]]:
    by_uci = {str(item.get("moveUci")): item for item in recommendations}
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for move_uci in ordered_moves:
        item = by_uci.get(move_uci)
        if item is None or move_uci in seen:
            continue
        result.append(item)
        seen.add(move_uci)
    for item in recommendations:
        move_uci = str(item.get("moveUci"))
        if move_uci not in seen:
            result.append(item)
    return result


def _status(
    status: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    latency_ms: int = 0,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    resolved_provider = provider or os.getenv("AI_RERANK_PROVIDER", "gemini").lower().strip()
    return {
        "provider": resolved_provider,
        "model": model if model is not None else _model_for_provider(resolved_provider),
        "status": status,
        "latencyMs": latency_ms,
        "fallbackReason": fallback_reason,
    }


def _model_for_provider(provider: str) -> str | None:
    if provider == "gemini":
        return os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    if provider in {"openai-compatible", "openrouter", "groq", "openai"}:
        return os.getenv("AI_RERANK_MODEL")
    return None


def _default_base_url(provider: str) -> str | None:
    if provider == "openai":
        return "https://api.openai.com/v1"
    if provider == "openrouter":
        return "https://openrouter.ai/api/v1"
    if provider == "groq":
        return "https://api.groq.com/openai/v1"
    return None


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _elapsed_ms(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))
