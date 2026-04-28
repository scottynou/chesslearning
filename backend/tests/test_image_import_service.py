import chess

from app.image_import_service import response_from_detection


def test_response_from_detection_builds_valid_fen_with_castling() -> None:
    response = response_from_detection(
        {
            "piecePlacement": chess.STARTING_BOARD_FEN,
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
