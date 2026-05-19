"""
PGN Formatter
==============
Module 3 of the Chess Scoresheet → PGN Pipeline.

Consumes a ValidatedGame (from Module 2) and produces a standards-compliant
.pgn file following the PGN Standard (Portable Game Notation Specification
and Implementation Guide, 1994).

PGN standard references
────────────────────────
  • Seven Tag Roster (STR): mandatory headers in mandatory order.
  • Move text: "1. e4 e5 2. Nf3 Nc6" – full move number before White, no
    number before Black unless Black is the first move after a gap.
  • Line length ≤ 80 characters (hard wrap at token boundary).
  • Result termination marker: "1-0", "0-1", "1/2-1/2", or "*".
  • Annotation / NAG support (optional).
  • Comments in curly braces for flagged / corrected moves.

Author  : Senior Chess Engine Engineer
Version : 1.0.0
"""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

# Module 2 types (import only the data classes; engine not needed here)
from validation_engine import MoveStatus, ValidatedGame, ValidatedMove


# ════════════════════════════════════════════════════════════════════════════
# PGN Header
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class PGNHeaders:
    """
    Seven Tag Roster (STR) – all seven are mandatory in the PGN standard.
    Additional custom tags can be supplied via `extra`.
    """
    event  : str = "?"
    site   : str = "?"
    date   : str = "????.??.??"     # PGN date format: YYYY.MM.DD
    round  : str = "?"
    white  : str = "?"
    black  : str = "?"
    result : str = "*"              # "*" = game in progress / unknown

    extra  : Dict[str, str] = field(default_factory=dict)

    # ── Validation helpers ──────────────────────────────────────────────

    _VALID_RESULTS = {"1-0", "0-1", "1/2-1/2", "*"}
    _DATE_RE       = re.compile(r"^\d{4}\.\d{2}\.\d{2}$|^\?{4}\.\?{2}\.\?{2}$")

    def __post_init__(self) -> None:
        if self.result not in self._VALID_RESULTS:
            raise ValueError(
                f"Invalid PGN result '{self.result}'. "
                f"Must be one of: {self._VALID_RESULTS}"
            )
        # Auto-format a plain date string  (YYYY-MM-DD → YYYY.MM.DD)
        self.date = self.date.replace("-", ".")
        if not self._DATE_RE.match(self.date):
            raise ValueError(
                f"Invalid PGN date '{self.date}'. "
                f"Expected format YYYY.MM.DD or ????.??.??"
            )

    @classmethod
    def today(cls, **kwargs) -> "PGNHeaders":
        """Factory that fills the date field with today's date."""
        return cls(date=date.today().strftime("%Y.%m.%d"), **kwargs)

    def render(self) -> str:
        """Return the STR block as a multi-line string."""
        # STR must appear in this exact order per the PGN standard
        str_tags = [
            ("Event",  self.event),
            ("Site",   self.site),
            ("Date",   self.date),
            ("Round",  self.round),
            ("White",  self.white),
            ("Black",  self.black),
            ("Result", self.result),
        ]
        lines = [f'[{tag} "{value}"]' for tag, value in str_tags]

        # Non-STR supplemental tags (alphabetical, after a blank line)
        if self.extra:
            lines.append("")
            for tag in sorted(self.extra):
                lines.append(f'[{tag} "{self.extra[tag]}"]')

        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════
# Move Token Builder
# ════════════════════════════════════════════════════════════════════════════

class MoveTokeniser:
    """
    Converts a flat list of ValidatedMove objects into a sequence of PGN
    tokens ready for line-wrapping and file output.

    PGN token grammar (simplified):
        token   ::= move_number | san | comment | nag | result
        move_number ::= integer "."       (White)
                      | integer "..."     (Black, after gap only)
    """

    # Standard Annotation Glyphs for confidence-based annotation
    _NAG_DUBIOUS   = "$6"    # dubious move (low OCR confidence)
    _NAG_UNKNOWN   = "$0"    # null move placeholder
    _CONF_THRESHOLD = 0.55   # below this → annotate with NAG

    def build(
        self,
        moves: List[ValidatedMove],
        annotate_corrections: bool = True,
        annotate_low_confidence: bool = True,
    ) -> List[str]:
        """
        Returns an ordered list of PGN token strings.
        Comments are wrapped in { }.
        """
        tokens: List[str] = []
        need_black_number = False   # True after an UNKNOWN White move

        for i, move in enumerate(moves):
            is_white = move.side == "white"

            # ── Move number token ─────────────────────────────────────────
            if is_white:
                tokens.append(f"{move.move_number}.")
                need_black_number = False
            elif need_black_number:
                tokens.append(f"{move.move_number}...")
                need_black_number = False

            # ── SAN token ────────────────────────────────────────────────
            tokens.append(move.san)

            # ── NAG for low-confidence reads ──────────────────────────────
            if annotate_low_confidence and move.confidence < self._CONF_THRESHOLD:
                tokens.append(self._NAG_DUBIOUS)

            # ── Comment for corrections and unknowns ──────────────────────
            if annotate_corrections and move.status == MoveStatus.CORRECTED:
                comment = f"OCR read '{move.ocr_text}'; corrected: {move.correction}"
                tokens.append("{" + _escape_pgn_comment(comment) + "}")

            if move.status in (MoveStatus.UNKNOWN, MoveStatus.MISSING):
                tokens.append("{" + _escape_pgn_comment(move.correction) + "}")
                if is_white:
                    # Black move number must be re-stated after a White unknown
                    need_black_number = True

        return tokens


# ════════════════════════════════════════════════════════════════════════════
# PGN Line Wrapper  (≤ 80 chars per PGN spec)
# ════════════════════════════════════════════════════════════════════════════

def _wrap_tokens(tokens: List[str], line_width: int = 79) -> str:
    """
    Join tokens with single spaces, hard-wrapping at token boundaries so
    no line exceeds `line_width` characters.
    """
    lines: List[str] = []
    current = ""

    for token in tokens:
        candidate = f"{current} {token}".lstrip()
        if len(candidate) > line_width and current:
            lines.append(current)
            current = token
        else:
            current = candidate

    if current:
        lines.append(current)

    return "\n".join(lines)


def _escape_pgn_comment(text: str) -> str:
    """Comments may not contain { or } per the PGN standard."""
    return text.replace("{", "(").replace("}", ")")


# ════════════════════════════════════════════════════════════════════════════
# PGN Formatter – main class
# ════════════════════════════════════════════════════════════════════════════

class PGNFormatter:
    """
    Orchestrates header generation, move-text formatting, and file export.

    Usage
    -----
    headers = PGNHeaders.today(
        event="City Open 2025", site="Chennai", round="3",
        white="Arjun, V.", black="Priya, S.", result="1-0",
    )
    formatter = PGNFormatter(headers, annotate_corrections=True)
    pgn_str   = formatter.format(validated_game)
    formatter.save(validated_game, "output/game.pgn")
    """

    def __init__(
        self,
        headers: PGNHeaders,
        annotate_corrections: bool = True,
        annotate_low_confidence: bool = True,
        line_width: int = 79,
    ) -> None:
        self.headers                 = headers
        self.annotate_corrections    = annotate_corrections
        self.annotate_low_confidence = annotate_low_confidence
        self.line_width              = line_width
        self._tokeniser              = MoveTokeniser()

    # ── Public API ──────────────────────────────────────────────────────

    def format(self, game: ValidatedGame) -> str:
        """
        Build and return the complete PGN string for a single game.
        Follows the PGN standard structure:
            <header block>
            <blank line>
            <move text section>
            <result token>
            <blank line>   ← required between games in a multi-game file
        """
        header_block = self.headers.render()
        move_tokens  = self._tokeniser.build(
            game.moves,
            annotate_corrections=self.annotate_corrections,
            annotate_low_confidence=self.annotate_low_confidence,
        )
        move_tokens.append(self.headers.result)   # termination marker
        move_section = _wrap_tokens(move_tokens, self.line_width)

        return f"{header_block}\n\n{move_section}\n"

    def save(self, game: ValidatedGame, path: str) -> None:
        """
        Write the PGN to disk.
        Encoding: UTF-8 with BOM omitted (standard PGN uses Latin-1 / ASCII
        for maximum compatibility, but UTF-8 without BOM is widely accepted).
        """
        pgn_str = self.format(game)
        out     = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)

        with out.open("w", encoding="utf-8", newline="\n") as f:
            f.write(pgn_str)

        print(f"✓  PGN saved → {out}  ({out.stat().st_size} bytes)")

    def append(self, game: ValidatedGame, path: str) -> None:
        """
        Append a game to an existing PGN file (multi-game PGN).
        Creates the file if it does not exist.
        """
        pgn_str = self.format(game)
        out     = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)

        with out.open("a", encoding="utf-8", newline="\n") as f:
            f.write("\n" + pgn_str)

        print(f"✓  Game appended → {out}")

    # ── Convenience: format from raw validated JSON ──────────────────────

    @classmethod
    def from_validated_json(
        cls,
        json_path: str,
        headers: PGNHeaders,
        **kwargs,
    ) -> str:
        """Load a validated_game.json (Module 2 output) and return PGN string."""
        data   = json.loads(Path(json_path).read_text(encoding="utf-8"))
        moves  = [_dict_to_validated_move(m) for m in data["moves"]]
        flags  = data.get("flags", [])

        # Embed pipeline warnings as a PGN game comment
        if flags:
            kwargs.setdefault("annotate_corrections", True)

        formatter = cls(headers, **kwargs)
        # Reconstruct a minimal ValidatedGame shell
        from validation_engine import ValidatedGame
        game = ValidatedGame(moves=moves, flags=flags)
        return formatter.format(game)


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def _dict_to_validated_move(d: dict) -> ValidatedMove:
    return ValidatedMove(
        move_number=d["move_number"],
        side=d["side"],
        ocr_text=d.get("ocr_text", ""),
        san=d["san"],
        uci=d.get("uci", ""),
        status=MoveStatus[d["status"]],
        correction=d.get("correction", ""),
        confidence=float(d.get("confidence", 1.0)),
    )


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════

def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="PGN Formatter – Chess Scoresheet Pipeline Module 3",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("validated_json",
                        help="validated_game.json produced by Module 2")
    parser.add_argument("--out",     default="output/game.pgn",
                        help="Output .pgn file path")
    # STR header fields
    parser.add_argument("--event",   default="?")
    parser.add_argument("--site",    default="?")
    parser.add_argument("--date",    default=date.today().strftime("%Y.%m.%d"))
    parser.add_argument("--round",   default="?")
    parser.add_argument("--white",   default="?")
    parser.add_argument("--black",   default="?")
    parser.add_argument("--result",  default="*",
                        choices=["1-0", "0-1", "1/2-1/2", "*"])
    parser.add_argument("--no-annotations", action="store_true",
                        help="Suppress correction comments in PGN output")
    args = parser.parse_args()

    headers = PGNHeaders(
        event=args.event,
        site=args.site,
        date=args.date,
        round=args.round,
        white=args.white,
        black=args.black,
        result=args.result,
    )

    pgn_str = PGNFormatter.from_validated_json(
        args.validated_json,
        headers=headers,
        annotate_corrections=not args.no_annotations,
    )

    print("\n── PGN Preview ────────────────────────────────────")
    print(pgn_str[:600])
    if len(pgn_str) > 600:
        print("  … (truncated)")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write(pgn_str)
    print(f"\n✓  PGN saved → {out}  ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    _cli()
