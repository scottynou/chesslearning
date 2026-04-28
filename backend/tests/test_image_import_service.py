import chess

from app.image_import_service import response_from_detection


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
