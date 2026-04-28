from __future__ import annotations

import json
import os
from typing import Any

import chess
import httpx

from .schemas import ImportPositionImageRequest, ImportPositionImageResponse


IMAGE_IMPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "piecePlacement": {
            "type": "string",
            "description": "FEN piece placement only, 8 ranks from rank 8 to rank 1.",
        },
        "sideToMove": {
            "type": "string",
            "enum": ["white", "black", "unknown"],
        },
        "boardOrientation": {
            "type": "string",
            "enum": ["white_bottom", "black_bottom", "unknown"],
        },
        "confidence": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
        },
        "warnings": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["piecePlacement", "sideToMove", "boardOrientation", "confidence", "warnings"],
}


def import_position_image(request: ImportPositionImageRequest) -> ImportPositionImageResponse:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("missing_gemini_api_key")

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    timeout_seconds = _float_env("IMAGE_IMPORT_TIMEOUT_SECONDS", 8.0)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    response = httpx.post(
        url,
        headers={"x-goog-api-key": api_key},
        json={
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": _prompt()},
                        {
                            "inline_data": {
                                "mime_type": request.mime_type,
                                "data": request.image_data,
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": IMAGE_IMPORT_SCHEMA,
            },
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    payload = json.loads(text)
    return response_from_detection(payload, provider="gemini", model=model)


def response_from_detection(payload: dict[str, Any], *, provider: str, model: str) -> ImportPositionImageResponse:
    placement = str(payload.get("piecePlacement", "")).strip()
    side_to_move = str(payload.get("sideToMove", "unknown")).strip().lower()
    if side_to_move not in {"white", "black"}:
        side_to_move = "white"
    turn = "w" if side_to_move == "white" else "b"
    castling = _castling_rights_from_placement(placement)
    fen = f"{placement} {turn} {castling} - 0 1"
    board = chess.Board(fen)
    if board.king(chess.WHITE) is None or board.king(chess.BLACK) is None or not board.is_valid():
        raise ValueError("detected_position_is_not_a_valid_chess_board")

    warnings = [str(item) for item in payload.get("warnings", []) if str(item).strip()]
    if payload.get("sideToMove") == "unknown":
        warnings.append("Trait non visible sur l'image; les blancs sont selectionnes par defaut.")

    board_orientation = str(payload.get("boardOrientation", "unknown")).strip().lower()
    if board_orientation not in {"white_bottom", "black_bottom", "unknown"}:
        board_orientation = "unknown"

    return ImportPositionImageResponse(
        fen=fen,
        sideToMove=side_to_move,
        boardOrientation=board_orientation,
        confidence=_clamp_int(payload.get("confidence", 0), 0, 100),
        warnings=warnings[:4],
        provider=provider,
        model=model,
    )


def _castling_rights_from_placement(placement: str) -> str:
    try:
        board = chess.Board(f"{placement} w - - 0 1")
    except ValueError:
        return "-"

    rights = ""
    if board.piece_at(chess.E1) == chess.Piece(chess.KING, chess.WHITE):
        if board.piece_at(chess.H1) == chess.Piece(chess.ROOK, chess.WHITE):
            rights += "K"
        if board.piece_at(chess.A1) == chess.Piece(chess.ROOK, chess.WHITE):
            rights += "Q"
    if board.piece_at(chess.E8) == chess.Piece(chess.KING, chess.BLACK):
        if board.piece_at(chess.H8) == chess.Piece(chess.ROOK, chess.BLACK):
            rights += "k"
        if board.piece_at(chess.A8) == chess.Piece(chess.ROOK, chess.BLACK):
            rights += "q"
    return rights or "-"


def _prompt() -> str:
    return (
        "Read the chessboard position from this screenshot. Return JSON only. "
        "Use standard chess FEN piece placement from White's perspective, rank 8 to rank 1, regardless of the screenshot orientation. "
        "Detect whether the board is shown with white pieces at the bottom or black pieces at the bottom when possible. "
        "If the screenshot clearly shows whose turn it is, set sideToMove to white or black; otherwise set unknown. "
        "Do not infer move history. Do not include explanations. If a square is obscured, choose the most likely legal piece and lower confidence."
    )


def _clamp_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = minimum
    return max(minimum, min(maximum, parsed))


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default
