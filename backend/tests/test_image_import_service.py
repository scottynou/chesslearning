import json

import chess
import httpx
from fastapi.testclient import TestClient

from app.image_import_service import ImageImportProviderError, import_position_image, response_from_detection
from app.schemas import ImportPositionImageRequest


def test_response_from_detection_builds_valid_fen_with_castling() -> None:
    response = response_from_detection(
        {
            "visibleRows": [
                "rnbqkbnr",
                "pppppppp",
                "........",
                "........",
                "........",
                "........",
                "PPPPPPPP",
                "RNBQKBNR",
            ],
            "sideToMove": "white",
            "boardOrientation": "white_bottom",
            "confidence": 94,
            "warnings": [],
        },
        provider="gemini",
        model="test-model",
    )

    assert response.fen == chess.STARTING_FEN
    assert response.side_to_move == "white"
    assert response.board_orientation == "white_bottom"


def test_response_from_detection_rotates_black_bottom_visible_rows() -> None:
    response = response_from_detection(
        {
            "visibleRows": [
                "RNBKQBNR",
                "PPPPPPPP",
                "........",
                "........",
                "........",
                "........",
                "pppppppp",
                "rnbkqbnr",
            ],
            "sideToMove": "black",
            "boardOrientation": "black_bottom",
            "confidence": 91,
            "warnings": [],
        },
        provider="gemini",
        model="test-model",
    )

    assert response.fen == f"{chess.STARTING_BOARD_FEN} b KQkq - 0 1"
    assert response.board_orientation == "black_bottom"


def test_response_from_detection_infers_orientation_from_kings() -> None:
    response = response_from_detection(
        {
            "visibleRows": [
                "RNBKQBNR",
                "PPPPPPPP",
                "........",
                "........",
                "........",
                "........",
                "pppppppp",
                "rnbkqbnr",
            ],
            "sideToMove": "white",
            "boardOrientation": "unknown",
            "confidence": 72,
            "warnings": [],
        },
        provider="gemini",
        model="test-model",
    )

    assert response.fen == chess.STARTING_FEN
    assert response.board_orientation == "black_bottom"


def test_response_from_detection_defaults_unknown_turn_to_white() -> None:
    response = response_from_detection(
        {
            "piecePlacement": chess.STARTING_BOARD_FEN,
            "sideToMove": "unknown",
            "boardOrientation": "unknown",
            "confidence": 40,
            "warnings": [],
        },
        provider="gemini",
        model="test-model",
    )

    assert response.fen.split()[1] == "w"
    assert response.warnings


def test_import_position_image_falls_back_to_second_model(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_IMPORT_MODEL", "primary-model")
    monkeypatch.setenv("GEMINI_MODEL", "fallback-model")
    calls: list[str] = []

    class FakeGeminiResponse:
        def __init__(self, url: str):
            self.url = url

        def raise_for_status(self) -> None:
            if "primary-model" in self.url or "gemini-2.5-flash" in self.url:
                response = httpx.Response(429, request=httpx.Request("POST", self.url))
                raise httpx.HTTPStatusError("quota", request=response.request, response=response)

        def json(self) -> dict:
            payload = {
                "visibleRows": [
                    "rnbqkbnr",
                    "pppppppp",
                    "........",
                    "........",
                    "........",
                    "........",
                    "PPPPPPPP",
                    "RNBQKBNR",
                ],
                "sideToMove": "white",
                "boardOrientation": "white_bottom",
                "confidence": 88,
                "warnings": [],
            }
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}

    def fake_post(url: str, **_: object) -> FakeGeminiResponse:
        calls.append(url)
        return FakeGeminiResponse(url)

    import app.image_import_service as image_import_service

    monkeypatch.setattr(image_import_service.httpx, "post", fake_post)

    response = import_position_image(
        ImportPositionImageRequest(imageData="a" * 96, mimeType="image/jpeg", fileName="board.jpg")
    )

    assert response.model == "fallback-model"
    assert len(calls) == 2


def test_import_position_image_uses_one_lightweight_detection_pass(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_IMPORT_MODEL", "vision-model")
    calls = 0

    class FakeGeminiResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            nonlocal calls
            calls += 1
            payload = {
                "visibleRows": [
                    "rnbqkbnr",
                    "pppppppp",
                    "........",
                    "........",
                    "........",
                    "........",
                    "PPPPPPPP",
                    "RNBQKBNR",
                ],
                "sideToMove": "white",
                "boardOrientation": "white_bottom",
                "confidence": 86,
                "warnings": [],
            }
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}

    import app.image_import_service as image_import_service

    monkeypatch.setattr(image_import_service.httpx, "post", lambda *_, **__: FakeGeminiResponse())

    response = import_position_image(
        ImportPositionImageRequest(imageData="a" * 96, mimeType="image/jpeg", fileName="board.jpg")
    )

    assert response.fen == chess.STARTING_FEN
    assert calls == 1


def test_import_position_image_uses_valid_candidate_board(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_IMPORT_MODEL", "vision-model")

    payload = {
        "visibleRows": [
            "rnbqkbnr",
            "pppppppp",
            "........",
            "........",
            "........",
            "........",
            "PPPPPPPP",
            "RNBQ.BNR",
        ],
        "sideToMove": "white",
        "boardOrientation": "white_bottom",
        "confidence": 40,
        "warnings": [],
        "candidateBoards": [
            {
                "visibleRows": [
                    "rnbqkbnr",
                    "pppppppp",
                    "........",
                    "........",
                    "........",
                    "........",
                    "PPPPPPPP",
                    "RNBQKBNR",
                ],
                "sideToMove": "white",
                "boardOrientation": "white_bottom",
                "confidence": 82,
                "warnings": [],
            }
        ],
    }

    class FakeGeminiResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}

    import app.image_import_service as image_import_service

    monkeypatch.setattr(image_import_service.httpx, "post", lambda *_, **__: FakeGeminiResponse())

    response = import_position_image(
        ImportPositionImageRequest(imageData="a" * 96, mimeType="image/jpeg", fileName="board.jpg")
    )

    assert response.fen == chess.STARTING_FEN
    assert response.confidence == 82


def test_import_position_image_endpoint_returns_readable_provider_error(monkeypatch) -> None:
    import app.main as main

    def fake_import_position_image(_: ImportPositionImageRequest):
        raise ImageImportProviderError("Import image temporairement indisponible: quota Gemini atteint.", status_code=429)

    monkeypatch.setattr(main, "import_position_image", fake_import_position_image)
    client = TestClient(main.app)

    response = client.post(
        "/import-position-image",
        json={"imageData": "a" * 96, "mimeType": "image/jpeg", "fileName": "board.jpg"},
    )

    assert response.status_code == 429
    assert response.json()["detail"] == "Import image temporairement indisponible: quota Gemini atteint."
