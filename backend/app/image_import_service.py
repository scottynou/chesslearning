from __future__ import annotations

import json
import os
from typing import Any

import chess
import httpx

from .schemas import ImportPositionImageRequest, ImportPositionImageResponse


class ImageImportProviderError(RuntimeError):
    def __init__(self, public_message: str, *, status_code: int = 502):
        super().__init__(public_message)
        self.public_message = public_message
        self.status_code = status_code


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
        "candidateBoards": {
            "type": "array",
            "description": "Optional extra candidate readings of the same board, ordered from most likely to least likely.",
            "items": {
                "type": "object",
                "properties": {
                    "piecePlacement": {"type": "string"},
                    "visibleRows": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 8,
                        "maxItems": 8,
                    },
                    "sideToMove": {"type": "string", "enum": ["white", "black", "unknown"]},
                    "boardOrientation": {"type": "string", "enum": ["white_bottom", "black_bottom", "unknown"]},
                    "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                    "warnings": {"type": "array", "items": {"type": "string"}},
                },
            },
            "maxItems": 3,
        },
    },
    "required": ["visibleRows", "sideToMove", "boardOrientation", "confidence", "warnings"],
}


def import_position_image(request: ImportPositionImageRequest) -> ImportPositionImageResponse:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ImageImportProviderError("Import image indisponible: cle Gemini absente sur le serveur.", status_code=503)

    timeout_seconds = _float_env("IMAGE_IMPORT_TIMEOUT_SECONDS", 180.0)
    models = _image_import_models()
    last_error: ImageImportProviderError | None = None
    for model in models:
        try:
            return _import_with_gemini_model(request, api_key=api_key, model=model, timeout_seconds=timeout_seconds)
        except ImageImportProviderError as exc:
            last_error = exc
            if exc.status_code not in {404, 408, 429, 500, 502, 503, 504}:
                break

    if last_error is not None:
        raise last_error
    raise ImageImportProviderError("Import image indisponible: aucun modele image configure.", status_code=503)


def _import_with_gemini_model(
    request: ImportPositionImageRequest,
    *,
    api_key: str,
    model: str,
    timeout_seconds: float,
) -> ImportPositionImageResponse:
    try:
        payload = _request_gemini_detection(
            request,
            api_key=api_key,
            model=model,
            prompt=_prompt(),
            timeout_seconds=timeout_seconds,
        )
        best = _best_response_from_payload(payload, provider="gemini", model=model)
        if best is None:
            raise ValueError("detected_position_is_not_a_valid_chess_board")
        if not _is_high_confidence_response(best):
            best.warnings.append("Reconnaissance automatique incertaine; corrige le plateau avant de valider.")
        return best
    except httpx.HTTPStatusError as exc:
        raise ImageImportProviderError(_provider_status_message(exc.response.status_code), status_code=exc.response.status_code) from exc
    except httpx.TimeoutException as exc:
        raise ImageImportProviderError("Import image indisponible: Gemini met trop de temps a repondre.", status_code=504) from exc
    except httpx.RequestError as exc:
        raise ImageImportProviderError("Import image indisponible: connexion impossible avec Gemini.", status_code=502) from exc
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ImageImportProviderError("Import image indisponible: Gemini a renvoye une reponse illisible.", status_code=502) from exc
    except ValueError as exc:
        raise ImageImportProviderError("Impossible de lire une position d'echecs fiable sur cette image.", status_code=422) from exc


def _request_gemini_detection(
    request: ImportPositionImageRequest,
    *,
    api_key: str,
    model: str,
    prompt: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    response = httpx.post(
        url,
        headers={"x-goog-api-key": api_key},
        json={
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}, *_image_parts(request)],
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
    return json.loads(text)


def _image_parts(request: ImportPositionImageRequest) -> list[dict[str, Any]]:
    variants = [
        {"label": "image complete originale", "mime_type": request.mime_type, "data": request.image_data},
        *[
            {
                "label": variant.label or f"crop candidat {index + 1}",
                "mime_type": variant.mime_type,
                "data": variant.image_data,
            }
            for index, variant in enumerate(request.image_variants[:4])
        ],
    ]

    parts: list[dict[str, Any]] = []
    for index, variant in enumerate(variants, start=1):
        parts.append({"text": f"Image {index}: {variant['label']}. Use the clearest image that contains the full 8x8 chessboard."})
        parts.append(
            {
                "inline_data": {
                    "mime_type": variant["mime_type"],
                    "data": variant["data"],
                }
            }
        )
    return parts


def _image_import_models() -> list[str]:
    configured = [
        os.getenv("IMAGE_IMPORT_MODEL"),
        os.getenv("GEMINI_MODEL"),
        "gemini-2.5-flash-lite",
    ]
    models: list[str] = []
    for model in configured:
        clean = (model or "").strip()
        if clean and clean not in models:
            models.append(clean)
    return models


def _responses_from_payloads(
    payloads: list[dict[str, Any]],
    *,
    provider: str,
    model: str,
) -> list[ImportPositionImageResponse]:
    responses: list[ImportPositionImageResponse] = []
    seen: set[tuple[str, str]] = set()
    for payload in payloads:
        for candidate in _candidate_payloads(payload):
            try:
                response = response_from_detection(candidate, provider=provider, model=model)
            except ValueError:
                continue
            key = (_position_key(response), response.side_to_move)
            if key in seen:
                continue
            seen.add(key)
            responses.append(response)
    return responses


def _best_consensus_response(responses: list[ImportPositionImageResponse]) -> ImportPositionImageResponse | None:
    if not responses:
        return None

    grouped: dict[str, list[ImportPositionImageResponse]] = {}
    for response in responses:
        grouped.setdefault(_position_key(response), []).append(response)

    best_group = max(
        grouped.values(),
        key=lambda group: (len(group), max(_response_score(item) for item in group)),
    )
    best = max(best_group, key=_response_score)
    if len(best_group) >= 2:
        return best
    return best if _response_score(best) >= 118 else None


def _position_key(response: ImportPositionImageResponse) -> str:
    try:
        board = chess.Board(response.fen)
        return board.board_fen()
    except ValueError:
        return response.fen.split(" ", 1)[0]


def _is_high_confidence_response(response: ImportPositionImageResponse) -> bool:
    try:
        board = chess.Board(response.fen)
    except ValueError:
        return False
    if not board.is_valid() and response.confidence < 92:
        return False
    return _response_score(response) >= 118


def _best_response_from_payload(payload: dict[str, Any], *, provider: str, model: str) -> ImportPositionImageResponse | None:
    best: ImportPositionImageResponse | None = None
    best_score = -1
    for candidate in _candidate_payloads(payload):
        try:
            response = response_from_detection(candidate, provider=provider, model=model)
        except ValueError:
            continue
        score = _response_score(response)
        if score > best_score:
            best = response
            best_score = score
    return best


def _candidate_payloads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [payload]
    raw_candidates = payload.get("candidateBoards")
    if isinstance(raw_candidates, list):
        for item in raw_candidates:
            if isinstance(item, dict):
                candidates.append({**payload, **item, "candidateBoards": []})
    return candidates


def _response_score(response: ImportPositionImageResponse) -> int:
    try:
        board = chess.Board(response.fen)
    except ValueError:
        return -1

    score = int(response.confidence)
    if board.is_valid():
        score += 45
    if response.board_orientation in {"white_bottom", "black_bottom"}:
        score += 10
    if "validation stricte incertaine" in " ".join(response.warnings):
        score -= 22
    piece_count = len(board.piece_map())
    if 2 <= piece_count <= 32:
        score += min(piece_count, 24)
    return score


def _provider_status_message(status_code: int) -> str:
    if status_code == 400:
        return "Import image refuse: image trop lourde, illisible ou format mal compris par Gemini."
    if status_code in {401, 403}:
        return "Import image indisponible: cle Gemini refusee ou API non autorisee."
    if status_code == 404:
        return "Import image indisponible: modele Gemini image introuvable."
    if status_code == 413:
        return "Import image refuse: image trop lourde apres compression."
    if status_code == 429:
        return "Import image temporairement indisponible: quota Gemini atteint, reessaie dans quelques instants."
    if status_code in {500, 502, 503, 504}:
        return "Import image temporairement indisponible: Gemini ne repond pas correctement."
    return "Import image indisponible: Gemini a refuse la demande."


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
    if _has_fatal_board_detection_error(board):
        raise ValueError("detected_position_is_not_a_valid_chess_board")

    warnings = [str(item) for item in payload.get("warnings", []) if str(item).strip()]
    if payload.get("sideToMove") == "unknown":
        warnings.append("Trait non visible sur l'image; les blancs sont selectionnes par defaut.")
    if payload.get("boardOrientation") == "unknown":
        warnings.append("Orientation estimee automatiquement; verifie le plateau avant de jouer.")
    if not board.is_valid():
        warnings.append("Position lue mais validation stricte incertaine; verifie les pieces avant de jouer.")

    return ImportPositionImageResponse(
        fen=fen,
        sideToMove=side_to_move,
        boardOrientation=board_orientation,
        confidence=_clamp_int(payload.get("confidence", 0), 0, 100),
        warnings=warnings[:4],
        provider=provider,
        model=model,
    )


def _has_fatal_board_detection_error(board: chess.Board) -> bool:
    if board.king(chess.WHITE) is None or board.king(chess.BLACK) is None:
        return True
    if bool(board.pawns & chess.BB_BACKRANKS):
        return True
    if len(board.piece_map()) > 32:
        return True
    if len(board.pieces(chess.PAWN, chess.WHITE)) > 8 or len(board.pieces(chess.PAWN, chess.BLACK)) > 8:
        return True
    return False


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
        "Read the chessboard position from this screenshot. Return JSON only. Accuracy is much more important than speed. "
        "You may receive the original image and several crop candidates. Use the clearest image that shows the entire 8x8 chessboard. "
        "First identify the 8x8 board edges. Ignore arrows, highlights, move dots, coordinates, clocks, side panels, and UI text. "
        "Then read the pieces square by square exactly as they appear on the screen. Work row by row and check every square twice. "
        "Return visibleRows as 8 strings from the screenshot top row to bottom row, each string left to right on the screenshot. "
        "Each visibleRows string must have exactly 8 characters: KQRBNP for white pieces, kqrbnp for black pieces, and . for empty squares. "
        "Also return up to 3 candidateBoards if any piece or orientation is ambiguous. "
        "Do not rotate visibleRows yourself. If the board is rotated, still write what the viewer sees from top-left to bottom-right. "
        "Set boardOrientation to white_bottom if White's back rank/pieces are at the bottom of the screenshot, black_bottom if Black's are at the bottom, otherwise unknown. "
        "piecePlacement is optional and can repeat the final FEN placement, but visibleRows is the source of truth. "
        "If the screenshot clearly shows whose turn it is, set sideToMove to white or black; otherwise set unknown. "
        "Do not infer move history. Do not include explanations. If a square is obscured, choose the most likely piece and lower confidence."
    )


def _verification_prompt(best_fen: str, previous_payload: dict[str, Any]) -> str:
    previous = json.dumps(previous_payload, ensure_ascii=True)[:2400]
    return (
        f"{_prompt()} This is a verification pass. A previous pass produced FEN: {best_fen}. "
        f"Previous raw JSON was: {previous}. "
        "Do not trust the previous answer blindly. Compare it against the image square by square. "
        "Correct any wrong piece, missing piece, swapped king/queen, knight/bishop confusion, color inversion, or board rotation. "
        "Return the final corrected visibleRows and optional candidateBoards."
    )


def _independent_second_pass_prompt() -> str:
    return (
        "Read the chessboard position from this screenshot as an independent second pass. Return JSON only. "
        "Do not rely on any previous answer. Treat this like forensic visual transcription. "
        "Find the board corners, ignore highlights/arrows/UI, determine orientation, then inspect every square twice. "
        "For each occupied square, decide piece type and color from the glyph shape, not from move legality. "
        "Return visibleRows from screen top to bottom, left to right, using KQRBNP/kqrbnp/empty dots. "
        "If there are two plausible readings, put the alternatives in candidateBoards. "
        "Accuracy matters more than speed; take your time."
    )


def _repair_prompt(previous_payload: dict[str, Any]) -> str:
    previous = json.dumps(previous_payload, ensure_ascii=True)[:1800]
    return (
        f"{_prompt()} The previous detection was rejected as an invalid chess position: {previous}. "
        "Retry from the image itself, not from memory. Make sure the final board has exactly one white king and one black king, "
        "no pawns on the first or eighth rank unless clearly visible from a variant screenshot, and no more than 8 pieces per row. "
        "If a piece is ambiguous, prefer the normal legal chess piece that makes the whole board valid."
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
