"""
Chess Validation & Merging Engine
===================================
Module 2 of the Chess Scoresheet → PGN Pipeline.

Consumes the JSON produced by Module 1 (scoresheet_pipeline.py), validates
every move against a live python-chess board, applies fuzzy correction for
OCR noise, merges both colour sequences, and emits a clean ValidatedGame.

Author  : Senior Chess Engine / NLP Engineer
Version : 1.0.0
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import chess
import chess.pgn

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# Data Model
# ════════════════════════════════════════════════════════════════════════════

class MoveStatus(Enum):
    OK          = auto()   # OCR text was directly legal
    CORRECTED   = auto()   # OCR text was illegal; fuzzy match found a fix
    UNKNOWN     = auto()   # Could not determine a legal move
    MISSING     = auto()   # One colour list was shorter than the other


@dataclass
class ValidatedMove:
    move_number : int
    side        : str           # "white" | "black"
    ocr_text    : str           # raw OCR string (may be empty for MISSING)
    san         : str           # final Standard Algebraic Notation
    uci         : str           # UCI string  (e.g. "e2e4")
    status      : MoveStatus
    correction  : str  = ""     # what was wrong and how it was fixed
    confidence  : float = 1.0   # propagated from OCR stage

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.name
        return d


@dataclass
class ValidatedGame:
    moves   : List[ValidatedMove] = field(default_factory=list)
    flags   : List[str]           = field(default_factory=list)  # human-readable warnings

    # Convenience ---------------------------------------------------------
    @property
    def unknown_moves(self) -> List[ValidatedMove]:
        return [m for m in self.moves if m.status in (MoveStatus.UNKNOWN, MoveStatus.MISSING)]

    @property
    def corrected_moves(self) -> List[ValidatedMove]:
        return [m for m in self.moves if m.status == MoveStatus.CORRECTED]

    def summary(self) -> str:
        total     = len(self.moves)
        ok        = sum(1 for m in self.moves if m.status == MoveStatus.OK)
        corrected = len(self.corrected_moves)
        unknown   = len(self.unknown_moves)
        return (
            f"Total: {total}  OK: {ok}  "
            f"Corrected: {corrected}  Unknown/Missing: {unknown}"
        )

    def to_json(self, path: str) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            json.dump(
                {"moves": [m.to_dict() for m in self.moves], "flags": self.flags},
                f, indent=2,
            )
        log.info("Validated game saved → %s", out)


# ════════════════════════════════════════════════════════════════════════════
# OCR Normaliser
# ════════════════════════════════════════════════════════════════════════════

class OCRNormaliser:
    """
    Applies deterministic, chess-aware substitutions to raw OCR text
    before passing it to the chess engine.

    All substitutions are documented so the correction log is meaningful.
    """

    # Ordered list of (pattern, replacement, description)
    _RULES: List[Tuple[str, str, str]] = [
        # Castling  ─────────────────────────────────────────────────────────
        (r"\b0-0-0\b",      "O-O-O",  "castling 0-0-0 → O-O-O"),
        (r"\b0-0\b",        "O-O",    "castling 0-0 → O-O"),
        (r"\bo-o-o\b",      "O-O-O",  "lower-case castling → O-O-O"),
        (r"\bo-o\b",        "O-O",    "lower-case castling → O-O"),

        # Piece letter confusions  ──────────────────────────────────────────
        (r"\bH([a-h][1-8])", r"N\1",  "H piece (OCR noise) → N (Knight)"),
        (r"\bh([a-h][1-8])", r"N\1",  "h piece (lowercase) → N (Knight)"),
        (r"\b[Ii]([a-h][1-8])", r"1\1", "I piece → rank digit 1"),
        (r"\bl([a-h][1-8])", r"1\1",  "l (lowercase L) as digit → 1"),

        # Check / mate symbols  ────────────────────────────────────────────
        (r"(\w)\s*\+\+",    r"\1#",   "++ (double-check notation) → #"),
        (r"ch\b",           "+",      "trailing 'ch' → '+'"),

        # Promotion – ensure no space between piece and '='  ───────────────
        (r"([a-h][18])\s*=\s*([QRBN])", r"\1=\2", "normalise promotion spacing"),

        # Stray OCR artefacts  ─────────────────────────────────────────────
        (r"[.…·•]",         "",       "strip stray punctuation"),
        (r"\s+",            "",       "strip internal whitespace"),
    ]

    def __init__(self) -> None:
        self._compiled = [
            (re.compile(pat, re.IGNORECASE if not pat[0].isupper() else 0), repl, desc)
            for pat, repl, desc in self._RULES
        ]

    def normalise(self, raw: str) -> Tuple[str, List[str]]:
        """
        Returns (normalised_text, list_of_applied_rule_descriptions).
        """
        text  = unicodedata.normalize("NFC", raw).strip()
        notes: List[str] = []

        for regex, repl, desc in self._compiled:
            new_text = regex.sub(repl, text)
            if new_text != text:
                notes.append(desc)
                text = new_text

        return text, notes


# ════════════════════════════════════════════════════════════════════════════
# Fuzzy Move Corrector
# ════════════════════════════════════════════════════════════════════════════

class FuzzyCorrector:
    """
    When a (normalised) OCR token is not directly parseable as a legal SAN
    move, this class attempts to identify the closest legal alternative.

    Strategy (applied in order until a match is found):
    ───────────────────────────────────────────────────
    1. Character-level edit distance (difflib) against all legal SAN strings.
    2. Destination-square rescue: extract the target square from the OCR
       text and find any legal move landing there.
    3. Return None if nothing plausible is found.
    """

    # Piece chars to try when the OCR piece letter is unrecognised
    _PIECE_SUBSTITUTIONS: Dict[str, List[str]] = {
        "H": ["N"],       "h": ["N"],
        "D": ["Q", "B"],  "d": ["Q", "B"],
        "I": ["1"],       "l": ["1"],
        "Z": ["2"],       "S": ["5"],
    }

    def correct(
        self,
        ocr_text: str,
        board: chess.Board,
    ) -> Optional[Tuple[chess.Move, str, str]]:
        """
        Parameters
        ----------
        ocr_text : normalised OCR string
        board    : current board state

        Returns
        -------
        (chess.Move, corrected_san, correction_note)  or  None
        """
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return None

        legal_sans = {board.san(m): m for m in legal_moves}

        # ── Strategy 1: edit-distance against all legal SANs ───────────────
        best = self._edit_distance_match(ocr_text, legal_sans)
        if best:
            move, san, score = best
            note = f"edit-distance correction '{ocr_text}' → '{san}' (score={score:.2f})"
            return move, san, note

        # ── Strategy 2: destination-square rescue ─────────────────────────
        sq_match = self._square_rescue(ocr_text, legal_sans, board)
        if sq_match:
            move, san = sq_match
            note = (
                f"square-rescue: OCR '{ocr_text}' → landed on target square, "
                f"best legal move = '{san}'"
            )
            return move, san, note

        return None

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _edit_distance_match(
        ocr_text: str,
        legal_sans: Dict[str, chess.Move],
        threshold: float = 0.55,
    ) -> Optional[Tuple[chess.Move, str, float]]:
        """
        Picks the legal SAN with the highest SequenceMatcher ratio.
        Returns None if best score < threshold.
        """
        best_san   = None
        best_score = 0.0

        for san in legal_sans:
            score = difflib.SequenceMatcher(None, ocr_text, san).ratio()
            if score > best_score:
                best_score = score
                best_san   = san

        if best_san and best_score >= threshold:
            return legal_sans[best_san], best_san, best_score
        return None

    @staticmethod
    def _extract_square(text: str) -> Optional[str]:
        """Pull the last valid board square from an OCR string (e.g. 'Hf3' → 'f3')."""
        m = re.search(r"([a-hA-H][1-8])", text)
        return m.group(1).lower() if m else None

    def _square_rescue(
        self,
        ocr_text: str,
        legal_sans: Dict[str, chess.Move],
        board: chess.Board,
    ) -> Optional[Tuple[chess.Move, str]]:
        sq_str = self._extract_square(ocr_text)
        if not sq_str:
            return None

        try:
            target_sq = chess.parse_square(sq_str)
        except ValueError:
            return None

        # Collect all legal moves landing on this square
        candidates = {
            san: move
            for san, move in legal_sans.items()
            if move.to_square == target_sq
        }

        if not candidates:
            return None

        if len(candidates) == 1:
            san, move = next(iter(candidates.items()))
            return move, san

        # Multiple candidates – prefer the one with the best edit distance
        best = self._edit_distance_match(ocr_text, candidates, threshold=0.0)
        if best:
            move, san, _ = best
            return move, san

        return None


# ════════════════════════════════════════════════════════════════════════════
# Validation Engine
# ════════════════════════════════════════════════════════════════════════════

class ValidationEngine:
    """
    Core engine: validates and corrects a single colour's move list
    against a progressive board state.
    """

    def __init__(self) -> None:
        self._normaliser = OCRNormaliser()
        self._corrector  = FuzzyCorrector()

    def validate_sequence(
        self,
        ocr_moves: List[dict],
        board: chess.Board,
        side: str,
    ) -> List[ValidatedMove]:
        """
        Walk through every OCR move for one colour, attempt to apply it,
        and return the validated sequence.

        The board is mutated in-place (caller owns the board state).
        """
        results: List[ValidatedMove] = []

        for raw in ocr_moves:
            move_num = raw.get("move_number", len(results) + 1)
            ocr_text = raw.get("move_text", "").strip()
            conf     = float(raw.get("confidence", 1.0))

            if not ocr_text:
                results.append(self._make_unknown(move_num, side, ocr_text, conf, "empty OCR text"))
                continue

            # ── Step 1: normalise ────────────────────────────────────────
            normed, norm_notes = self._normaliser.normalise(ocr_text)

            # ── Step 2: try direct parse ─────────────────────────────────
            move = self._try_parse(normed, board)
            if move:
                san = board.san(move)
                board.push(move)
                correction = "; ".join(norm_notes) if norm_notes else ""
                status     = MoveStatus.CORRECTED if norm_notes else MoveStatus.OK
                results.append(ValidatedMove(
                    move_number=move_num,
                    side=side,
                    ocr_text=ocr_text,
                    san=san,
                    uci=move.uci(),
                    status=status,
                    correction=correction,
                    confidence=conf,
                ))
                log.debug("[%s] move %d  %r → %s  (%s)",
                          side, move_num, ocr_text, san, status.name)
                continue

            # ── Step 3: fuzzy correction ─────────────────────────────────
            result = self._corrector.correct(normed, board)
            if result:
                move, san, note = result
                board.push(move)
                full_note = "; ".join(norm_notes + [note])
                results.append(ValidatedMove(
                    move_number=move_num,
                    side=side,
                    ocr_text=ocr_text,
                    san=san,
                    uci=move.uci(),
                    status=MoveStatus.CORRECTED,
                    correction=full_note,
                    confidence=conf,
                ))
                log.warning("[%s] move %d  CORRECTED  %r → %s  (%s)",
                            side, move_num, ocr_text, san, note)
                continue

            # ── Step 4: give up ──────────────────────────────────────────
            note = f"No legal move found for OCR text '{ocr_text}' (normalised: '{normed}')"
            log.error("[%s] move %d  UNKNOWN  %s", side, move_num, note)
            results.append(self._make_unknown(move_num, side, ocr_text, conf, note))
            # Do NOT push anything – board stays at last valid position.
            # This means subsequent moves are validated from an accurate state.

        return results

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _try_parse(san: str, board: chess.Board) -> Optional[chess.Move]:
        """Attempt SAN, UCI, and coordinate notations in order."""
        # SAN
        try:
            return board.parse_san(san)
        except (chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
            pass
        # UCI  (e.g. "e2e4")
        try:
            move = chess.Move.from_uci(san.lower())
            if move in board.legal_moves:
                return move
        except ValueError:
            pass
        return None

    @staticmethod
    def _make_unknown(
        move_num: int, side: str, ocr_text: str, conf: float, note: str
    ) -> ValidatedMove:
        return ValidatedMove(
            move_number=move_num,
            side=side,
            ocr_text=ocr_text,
            san="[UNKNOWN]",
            uci="",
            status=MoveStatus.UNKNOWN,
            correction=note,
            confidence=conf,
        )


# ════════════════════════════════════════════════════════════════════════════
# Merger
# ════════════════════════════════════════════════════════════════════════════

class GameMerger:
    """
    Merges independently validated White and Black move sequences into a
    single chronological game sequence, handling length mismatches gracefully.
    """

    def __init__(self) -> None:
        self._engine = ValidationEngine()

    def merge(
        self,
        white_ocr: List[dict],
        black_ocr: List[dict],
    ) -> ValidatedGame:
        """
        Validates both colour sequences against a shared board, then
        interleaves them: (W1, B1, W2, B2, …).

        Returns a ValidatedGame with all moves and any flags raised.
        """
        board = chess.Board()
        flags: List[str] = []

        # Validate White on the shared board (White goes first)
        white_validated = self._engine.validate_sequence(white_ocr, board, "white")

        # Black validation – board is now at the position after all White moves
        # We need to re-play from scratch interleaved, not sequentially by colour.
        # Solution: replay on a fresh board, alternating colours move-by-move.
        board2          = chess.Board()
        interleaved     = self._interleave_raw(white_ocr, black_ocr)
        interleaved_val = self._validate_interleaved(interleaved, board2)

        # Length mismatch detection
        if len(white_ocr) != len(black_ocr):
            diff = abs(len(white_ocr) - len(black_ocr))
            longer = "White" if len(white_ocr) > len(black_ocr) else "Black"
            flags.append(
                f"Move count mismatch: White={len(white_ocr)}, "
                f"Black={len(black_ocr)}. {longer} has {diff} extra move(s)."
            )

        # Propagate CORRECTED / UNKNOWN flags to the game-level flag list
        for m in interleaved_val:
            if m.status == MoveStatus.CORRECTED:
                flags.append(
                    f"Move {m.move_number} [{m.side}]: corrected '{m.ocr_text}' → "
                    f"'{m.san}'. Reason: {m.correction}"
                )
            elif m.status in (MoveStatus.UNKNOWN, MoveStatus.MISSING):
                flags.append(
                    f"Move {m.move_number} [{m.side}]: marked [UNKNOWN]. {m.correction}"
                )

        return ValidatedGame(moves=interleaved_val, flags=flags)

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _interleave_raw(
        white: List[dict],
        black: List[dict],
    ) -> List[dict]:
        """
        Create an interleaved list with explicit side labels and
        MISSING placeholders for the shorter sequence.
        """
        result: List[dict] = []
        max_len = max(len(white), len(black), 1)

        for i in range(max_len):
            if i < len(white):
                w = dict(white[i])
                w["side"] = "white"
                result.append(w)
            else:
                result.append({
                    "move_number": i + 1,
                    "side": "white",
                    "move_text": "",
                    "confidence": 0.0,
                    "_missing": True,
                })
            if i < len(black):
                b = dict(black[i])
                b["side"] = "black"
                result.append(b)
            else:
                result.append({
                    "move_number": i + 1,
                    "side": "black",
                    "move_text": "",
                    "confidence": 0.0,
                    "_missing": True,
                })

        return result

    def _validate_interleaved(
        self,
        interleaved: List[dict],
        board: chess.Board,
    ) -> List[ValidatedMove]:
        results: List[ValidatedMove] = []
        normaliser = OCRNormaliser()
        corrector  = FuzzyCorrector()
        engine     = ValidationEngine()

        for i, raw in enumerate(interleaved):
            move_num = raw.get("move_number", i // 2 + 1)
            side     = raw.get("side", "white")
            ocr_text = raw.get("move_text", "").strip()
            conf     = float(raw.get("confidence", 1.0))
            missing  = raw.get("_missing", False)

            # ── Missing placeholder ───────────────────────────────────────
            if missing or not ocr_text:
                results.append(ValidatedMove(
                    move_number=move_num,
                    side=side,
                    ocr_text="",
                    san="[UNKNOWN]",
                    uci="",
                    status=MoveStatus.MISSING if missing else MoveStatus.UNKNOWN,
                    correction="Move absent from OCR output.",
                    confidence=0.0,
                ))
                continue

            # ── Colour sanity check ───────────────────────────────────────
            expected_turn = chess.WHITE if side == "white" else chess.BLACK
            if board.turn != expected_turn:
                log.warning(
                    "Turn mismatch at interleaved index %d "
                    "(expected %s, board says %s). Skipping.",
                    i, side, "white" if board.turn else "black",
                )
                results.append(ValidatedMove(
                    move_number=move_num,
                    side=side,
                    ocr_text=ocr_text,
                    san="[UNKNOWN]",
                    uci="",
                    status=MoveStatus.UNKNOWN,
                    correction="Board turn mismatch – likely caused by a preceding UNKNOWN move.",
                    confidence=conf,
                ))
                continue

            # ── Normal validation path ────────────────────────────────────
            normed, norm_notes = normaliser.normalise(ocr_text)
            move = engine._try_parse(normed, board)

            if move:
                san        = board.san(move)
                board.push(move)
                status     = MoveStatus.CORRECTED if norm_notes else MoveStatus.OK
                correction = "; ".join(norm_notes)
                results.append(ValidatedMove(move_num, side, ocr_text, san,
                                             move.uci(), status, correction, conf))
                continue

            fix = corrector.correct(normed, board)
            if fix:
                move, san, note = fix
                board.push(move)
                full_note = "; ".join(norm_notes + [note])
                results.append(ValidatedMove(move_num, side, ocr_text, san,
                                             move.uci(), MoveStatus.CORRECTED,
                                             full_note, conf))
                continue

            # Give up
            note = f"No legal move for '{ocr_text}' (normalised: '{normed}')"
            results.append(ValidatedMove(move_num, side, ocr_text, "[UNKNOWN]",
                                         "", MoveStatus.UNKNOWN, note, conf))
            # Don't push – preserve board integrity for future moves

        return results


# ════════════════════════════════════════════════════════════════════════════
# Public façade
# ════════════════════════════════════════════════════════════════════════════

def validate_and_merge(
    white_moves: List[dict],
    black_moves: List[dict],
) -> ValidatedGame:
    """
    Convenience function — the only import most callers need.

    Parameters
    ----------
    white_moves, black_moves : lists of dicts as produced by Module 1.
        Each dict must have at minimum: 'move_number', 'move_text'.

    Returns
    -------
    ValidatedGame
    """
    return GameMerger().merge(white_moves, black_moves)


def load_moves_from_json(path: str) -> Tuple[List[dict], List[dict]]:
    """
    Helper: split a Module 1 JSON output by side.
    Expects the format: [ {move_number, side, move_text, confidence}, … ]
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    white = [m for m in data if m.get("side") == "white"]
    black = [m for m in data if m.get("side") == "black"]
    return white, black


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════

def _cli() -> None:
    import argparse, sys

    parser = argparse.ArgumentParser(
        description="Chess Validation & Merging Engine",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("moves_json",
                        help="JSON file from Module 1 (scoresheet_pipeline.py)")
    parser.add_argument("--out-json", default="output/validated_game.json",
                        help="Output path for validated game JSON")
    parser.add_argument("--verbose",  action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    white, black = load_moves_from_json(args.moves_json)
    log.info("Loaded %d White moves, %d Black moves.", len(white), len(black))

    game = validate_and_merge(white, black)

    print("\n── Validation Summary ─────────────────────────────")
    print(" ", game.summary())
    if game.flags:
        print("\n── Flags / Warnings ───────────────────────────────")
        for f in game.flags:
            print(f"  ⚑  {f}")

    print("\n── Move List (first 20) ────────────────────────────")
    for m in game.moves[:20]:
        status_tag = f"[{m.status.name}]" if m.status != MoveStatus.OK else ""
        print(f"  {m.move_number:>3}. [{m.side:<5}]  {m.san:<12} {status_tag}")

    game.to_json(args.out_json)


if __name__ == "__main__":
    _cli()
