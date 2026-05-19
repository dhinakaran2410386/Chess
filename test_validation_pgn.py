"""
Tests – Validation Engine & PGN Formatter
==========================================
Run with:  python -m pytest test_validation_pgn.py -v
"""

import json
import re
import tempfile
from pathlib import Path

import chess
import pytest

from validation_engine import (
    FuzzyCorrector,
    GameMerger,
    MoveStatus,
    OCRNormaliser,
    RawMove,
    ValidatedGame,
    ValidatedMove,
    ValidationEngine,
    validate_and_merge,
)
from pgn_formatter import (
    MoveTokeniser,
    PGNFormatter,
    PGNHeaders,
    _wrap_tokens,
)


# ════════════════════════════════════════════════════════════════════════════
# OCRNormaliser
# ════════════════════════════════════════════════════════════════════════════

class TestOCRNormaliser:

    def setup_method(self):
        self.n = OCRNormaliser()

    def _norm(self, text):
        return self.n.normalise(text)[0]

    def test_castling_zero(self):
        assert self._norm("0-0")   == "O-O"
        assert self._norm("0-0-0") == "O-O-O"

    def test_castling_lowercase(self):
        assert self._norm("o-o")   == "O-O"
        assert self._norm("o-o-o") == "O-O-O"

    def test_H_to_N(self):
        assert self._norm("Hf3") == "Nf3"
        assert self._norm("Hd5") == "Nd5"

    def test_double_check_to_mate(self):
        assert self._norm("e8++") == "e8#"

    def test_promotion_normalised(self):
        assert self._norm("e8 = Q") == "e8=Q"

    def test_notes_populated_on_change(self):
        _, notes = self.n.normalise("0-0")
        assert len(notes) > 0

    def test_notes_empty_on_no_change(self):
        _, notes = self.n.normalise("Nf3")
        assert notes == []


# ════════════════════════════════════════════════════════════════════════════
# FuzzyCorrector
# ════════════════════════════════════════════════════════════════════════════

class TestFuzzyCorrector:

    def setup_method(self):
        self.fc    = FuzzyCorrector()
        self.board = chess.Board()

    def test_Hf3_corrects_to_Nf3(self):
        result = self.fc.correct("Hf3", self.board)
        assert result is not None
        _, san, _ = result
        assert san == "Nf3"

    def test_e4_direct(self):
        # e4 is legal from start; edit distance from 'e4' to 'e4' = 1.0
        result = self.fc.correct("e4", self.board)
        assert result is not None
        _, san, _ = result
        assert san == "e4"

    def test_no_match_returns_none(self):
        result = self.fc.correct("XXXXXXX", self.board)
        assert result is None

    def test_square_rescue(self):
        # "Hf3" → the square f3 exists; Nf3 lands there
        result = self.fc.correct("Hf3", self.board)
        assert result is not None
        move, san, _ = result
        assert move.to_square == chess.F3

    def test_extract_square(self):
        assert FuzzyCorrector._extract_square("Hf3") == "f3"
        assert FuzzyCorrector._extract_square("xxxx") is None


# ════════════════════════════════════════════════════════════════════════════
# ValidationEngine (single colour)
# ════════════════════════════════════════════════════════════════════════════

class TestValidationEngine:

    def setup_method(self):
        self.engine = ValidationEngine()

    def _board(self):
        return chess.Board()

    def _raw(self, num, text, conf=1.0):
        return {"move_number": num, "move_text": text, "confidence": conf}

    def test_legal_move_ok(self):
        board  = self._board()
        result = self.engine.validate_sequence([self._raw(1, "e4")], board, "white")
        assert result[0].status == MoveStatus.OK
        assert result[0].san    == "e4"

    def test_correctable_move_corrected(self):
        board  = self._board()
        result = self.engine.validate_sequence([self._raw(1, "Hf3")], board, "white")
        assert result[0].status == MoveStatus.CORRECTED
        assert result[0].san    == "Nf3"

    def test_illegal_move_unknown(self):
        board  = self._board()
        result = self.engine.validate_sequence([self._raw(1, "Zz9")], board, "white")
        assert result[0].status == MoveStatus.UNKNOWN
        assert result[0].san    == "[UNKNOWN]"

    def test_board_advances_on_ok(self):
        board  = self._board()
        self.engine.validate_sequence([self._raw(1, "e4")], board, "white")
        assert board.fullmove_number == 1
        assert board.turn == chess.BLACK   # it is now Black's turn

    def test_board_not_advanced_on_unknown(self):
        board  = self._board()
        before_fen = board.fen()
        self.engine.validate_sequence([self._raw(1, "ZZZZ")], board, "white")
        assert board.fen() == before_fen


# ════════════════════════════════════════════════════════════════════════════
# GameMerger
# ════════════════════════════════════════════════════════════════════════════

class TestGameMerger:

    def _move(self, num, text, conf=1.0):
        return {"move_number": num, "move_text": text, "confidence": conf}

    def test_basic_interleave(self):
        white = [self._move(1, "e4"), self._move(2, "Nf3")]
        black = [self._move(1, "e5"), self._move(2, "Nc6")]
        game  = validate_and_merge(white, black)
        sides = [m.side for m in game.moves]
        assert sides == ["white", "black", "white", "black"]

    def test_mismatch_flagged(self):
        white = [self._move(1, "e4"), self._move(2, "Nf3")]
        black = [self._move(1, "e5")]
        game  = validate_and_merge(white, black)
        mismatch_flags = [f for f in game.flags if "mismatch" in f.lower()]
        assert len(mismatch_flags) == 1

    def test_short_black_gets_missing(self):
        white = [self._move(1, "e4"), self._move(2, "Nf3")]
        black = [self._move(1, "e5")]
        game  = validate_and_merge(white, black)
        missing = [m for m in game.moves if m.status == MoveStatus.MISSING]
        assert len(missing) >= 1
        assert missing[0].side == "black"

    def test_corrections_flagged(self):
        white = [self._move(1, "e4")]
        black = [self._move(1, "Hf6")]   # Hf6 → Nf6
        game  = validate_and_merge(white, black)
        corrected_flags = [f for f in game.flags if "corrected" in f.lower()]
        assert len(corrected_flags) >= 1

    def test_unknown_summary(self):
        white = [self._move(1, "ZZZZ")]
        black = [self._move(1, "e5")]
        game  = validate_and_merge(white, black)
        assert len(game.unknown_moves) >= 1

    def test_full_game_summary_str(self):
        white = [self._move(i, m) for i, m in enumerate(["e4", "Nf3", "Bb5"], 1)]
        black = [self._move(i, m) for i, m in enumerate(["e5", "Nc6", "a6"], 1)]
        game  = validate_and_merge(white, black)
        summary = game.summary()
        assert "Total" in summary


# ════════════════════════════════════════════════════════════════════════════
# PGNHeaders
# ════════════════════════════════════════════════════════════════════════════

class TestPGNHeaders:

    def test_str_block_has_seven_tags(self):
        h = PGNHeaders()
        rendered = h.render()
        tags = re.findall(r"^\[(\w+)", rendered, re.MULTILINE)
        assert tags[:7] == ["Event", "Site", "Date", "Round", "White", "Black", "Result"]

    def test_date_auto_converts_dashes(self):
        h = PGNHeaders(date="2025-06-01")
        assert h.date == "2025.06.01"

    def test_invalid_result_raises(self):
        with pytest.raises(ValueError, match="result"):
            PGNHeaders(result="2-0")

    def test_extra_tags_appear_after_str(self):
        h = PGNHeaders(extra={"ECO": "B20", "WhiteElo": "2400"})
        rendered = h.render()
        assert "[ECO" in rendered
        assert "[WhiteElo" in rendered

    def test_today_factory(self):
        h = PGNHeaders.today(white="Magnus", black="Hikaru")
        assert re.match(r"\d{4}\.\d{2}\.\d{2}", h.date)
        assert h.white == "Magnus"


# ════════════════════════════════════════════════════════════════════════════
# MoveTokeniser
# ════════════════════════════════════════════════════════════════════════════

class TestMoveTokeniser:

    def _make_move(self, num, side, san, status=MoveStatus.OK, ocr="", corr="", conf=1.0):
        return ValidatedMove(
            move_number=num, side=side, ocr_text=ocr,
            san=san, uci="", status=status, correction=corr, confidence=conf,
        )

    def test_white_gets_number_dot(self):
        moves  = [self._make_move(1, "white", "e4")]
        tokens = MoveTokeniser().build(moves)
        assert "1." in tokens

    def test_black_no_number_normally(self):
        moves = [
            self._make_move(1, "white", "e4"),
            self._make_move(1, "black", "e5"),
        ]
        tokens = MoveTokeniser().build(moves)
        # Should NOT have "1..." token
        assert "1..." not in tokens

    def test_black_gets_number_after_unknown_white(self):
        moves = [
            self._make_move(1, "white", "[UNKNOWN]", status=MoveStatus.UNKNOWN),
            self._make_move(1, "black", "e5"),
        ]
        tokens = MoveTokeniser().build(moves)
        assert "1..." in tokens

    def test_correction_comment_added(self):
        moves = [
            self._make_move(1, "white", "Nf3", status=MoveStatus.CORRECTED,
                            ocr="Hf3", corr="H→N substitution")
        ]
        tokens = MoveTokeniser().build(moves, annotate_corrections=True)
        comment_tokens = [t for t in tokens if t.startswith("{")]
        assert len(comment_tokens) == 1
        assert "Hf3" in comment_tokens[0]

    def test_low_confidence_nag(self):
        moves = [self._make_move(1, "white", "e4", conf=0.3)]
        tokens = MoveTokeniser().build(moves, annotate_low_confidence=True)
        assert "$6" in tokens


# ════════════════════════════════════════════════════════════════════════════
# _wrap_tokens
# ════════════════════════════════════════════════════════════════════════════

class TestWrapTokens:

    def test_no_line_exceeds_limit(self):
        tokens = ["1.", "e4", "e5", "2.", "Nf3", "Nc6", "3.", "Bb5", "a6", "1-0"]
        wrapped = _wrap_tokens(tokens, line_width=20)
        for line in wrapped.split("\n"):
            assert len(line) <= 20, f"Line too long: {line!r}"

    def test_single_token_not_wrapped(self):
        assert _wrap_tokens(["e4"], 10) == "e4"


# ════════════════════════════════════════════════════════════════════════════
# PGNFormatter – integration
# ════════════════════════════════════════════════════════════════════════════

class TestPGNFormatter:

    def _simple_game(self):
        white = [{"move_number": i, "move_text": m, "confidence": 1.0}
                 for i, m in enumerate(["e4", "Nf3", "Bb5"], 1)]
        black = [{"move_number": i, "move_text": m, "confidence": 1.0}
                 for i, m in enumerate(["e5", "Nc6", "a6"], 1)]
        return validate_and_merge(white, black)

    def _headers(self, **kw):
        return PGNHeaders(
            event="Test Event", site="Online", date="2025.06.01",
            round="1", white="Alice", black="Bob", result="*", **kw,
        )

    def test_pgn_contains_str_tags(self):
        game = self._simple_game()
        fmt  = PGNFormatter(self._headers())
        pgn  = fmt.format(game)
        assert '[Event "Test Event"]' in pgn
        assert '[White "Alice"]'      in pgn

    def test_pgn_contains_moves(self):
        game = self._simple_game()
        fmt  = PGNFormatter(self._headers())
        pgn  = fmt.format(game)
        assert "1." in pgn
        assert "e4"  in pgn

    def test_pgn_ends_with_result(self):
        game = self._simple_game()
        fmt  = PGNFormatter(self._headers())
        pgn  = fmt.format(game).strip()
        assert pgn.endswith("*")

    def test_pgn_saved_to_file(self, tmp_path):
        game = self._simple_game()
        fmt  = PGNFormatter(self._headers())
        out  = str(tmp_path / "game.pgn")
        fmt.save(game, out)
        content = Path(out).read_text(encoding="utf-8")
        assert "e4" in content
        assert content.strip().endswith("*")

    def test_no_annotations_suppresses_comments(self):
        white = [{"move_number": 1, "move_text": "Hf3", "confidence": 0.4}]
        black = [{"move_number": 1, "move_text": "e5",  "confidence": 1.0}]
        game  = validate_and_merge(white, black)
        fmt   = PGNFormatter(self._headers(), annotate_corrections=False,
                             annotate_low_confidence=False)
        pgn   = fmt.format(game)
        assert "{" not in pgn
        assert "$"  not in pgn

    def test_line_width_respected(self):
        game = self._simple_game()
        fmt  = PGNFormatter(self._headers(), line_width=40)
        pgn  = fmt.format(game)
        move_section = pgn.split("\n\n", 1)[1]   # skip headers
        for line in move_section.strip().split("\n"):
            assert len(line) <= 40, f"Line exceeds 40: {line!r}"

    def test_append_creates_multi_game_file(self, tmp_path):
        game = self._simple_game()
        fmt  = PGNFormatter(self._headers())
        out  = str(tmp_path / "multi.pgn")
        fmt.save(game, out)
        fmt.append(game, out)
        content = Path(out).read_text(encoding="utf-8")
        # Two copies of the Event tag means two games
        assert content.count('[Event "Test Event"]') == 2
