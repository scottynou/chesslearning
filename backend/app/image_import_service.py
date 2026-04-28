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
            "description": "Optional final FEN piece placement from White's perspective.",
        },
        "visibleRows": {
            "type": "array",
            "description": "Exactly what is visible on the screenshot: 8 rows from screen top to screen bottom, each row left to right. Use KQRBNP for white pieces, kqrbnp for black pieces, and . for empty squares.",
            "items": {"type": "string"},
            "minItems": 8,
            "maxItems": 8,
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
    "required": ["visibleRows", "sideToMove", "boardOrientation", "confidence", "warnings"],
}


def import_position_image(request: ImportPositionImageRequest) -> ImportPositionImageResponse:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("missing_gemini_api_key")

    model = os.getenv("IMAGE_IMPORT_MODEL") or os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
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
    board_orientation = str(payload.get("boardOrientation", "unknown")).strip().lower()
    if board_orientation not in {"white_bottom", "black_bottom", "unknown"}:
        board_orientation = "unknown"

    visible_rows = _normalize_visible_rows(payload.get("visibleRows"))
    if visible_rows is not None:
        board_orientation = _infer_orientation(visible_rows, board_orientation)
        placement = _visible_rows_to_piece_placement(visible_rows, board_orientation)
    else:
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
    if payload.get("boardOrientation") == "unknown":
        warnings.append("Orientation estimee automatiquement; verifie le plateau avant de jouer.")

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


def _normalize_visible_rows(value: Any) -> list[str] | None:
    if not isinstance(value, list) or len(value) != 8:
        return None

    normalized: list[str] = []
    for row in value:
        expanded = _expand_row(str(row))
        if expanded is None:
            return None
        normalized.append(expanded)
    return normalized


def _expand_row(row: str) -> str | None:
    clean = row.strip().replace(" ", "").replace("|", "").replace("-", ".").replace("_", ".")
    squares: list[str] = []
    for char in clean:
        if char in "KQRBNPkqrbnp.":
            squares.append(char)
        elif char.isdigit():
            squares.extend("." for _ in range(int(char)))
        else:
            return None
    if len(squares) != 8:
        return None
    return "".join(squares)


def _infer_orientation(visible_rows: list[str], board_orientation: str) -> str:
    if board_orientation in {"white_bottom", "black_bottom"}:
        return board_orientation

    white_king_row = _piece_row(visible_rows, "K")
    black_king_row = _piece_row(visible_rows, "k")
    if white_king_row is not None and black_king_row is not None:
        return "white_bottom" if white_king_row > black_king_row else "black_bottom"

    white_piece_rows = [index for index, row in enumerate(visible_rows) if any(char.isupper() for char in row)]
    black_piece_rows = [index for index, row in enumerate(visible_rows) if any(char.islower() for char in row)]
    if white_piece_rows and black_piece_rows:
        white_center = sum(white_piece_rows) / len(white_piece_rows)
        black_center = sum(black_piece_rows) / len(black_piece_rows)
        return "white_bottom" if white_center > black_center else "black_bottom"

    return "unknown"


def _piece_row(rows: list[str], piece: str) -> int | None:
    for index, row in enumerate(rows):
        if piece in row:
            return index
    return None


def _visible_rows_to_piece_placement(visible_rows: list[str], board_orientation: str) -> str:
    if board_orientation == "black_bottom":
        standard_rows = ["".join(reversed(row)) for row in reversed(visible_rows)]
    else:
        standard_rows = visible_rows
    return "/".join(_compress_row(row) for row in standard_rows)


def _compress_row(row: str) -> str:
    result = ""
    empty_count = 0
    for char in row:
        if char == ".":
            empty_count += 1
            continue
        if empty_count:
            result += str(empty_count)
            empty_count = 0
        result += char
    if empty_count:
        result += str(empty_count)
    return result


def _prompt() -> str:
    return (
        "Read the chessboard position from this screenshot. Return JSON only. Accuracy matters more than speed. "
        "First identify the 8x8 board edges. Then read the pieces square by square exactly as they appear on the screen. "
        "Return visibleRows as 8 strings from the screenshot top row to bottom row, each string left to right on the screenshot. "
        "Each visibleRows string must have exactly 8 characters: KQRBNP for white pieces, kqrbnp for black pieces, and . for empty squares. "
        "Do not rotate visibleRows yourself. If the board is rotated, still write what the viewer sees from top-left to bottom-right. "
        "Set boardOrientation to white_bottom if White's back rank/pieces are at the bottom of the screenshot, black_bottom if Black's are at the bottom, otherwise unknown. "
        "piecePlacement is optional and can repeat the final FEN placement, but visibleRows is the source of truth. "
        "If the screenshot clearly shows whose turn it is, set sideToMove to white or black; otherwise set unknown. "
        "Do not infer move history. Do not include explanations. If a square is obscured, choose the most likely piece and lower confidence."
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
