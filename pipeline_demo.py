"""
pipeline_demo.py
=================
End-to-end demonstration of the full Chess Scoresheet → PGN pipeline.

Simulates realistic OCR output (with intentional noise) and walks the
data through all three modules:

  Module 1 output  →  Module 2 (validation_engine.py)
                   →  Module 3 (pgn_formatter.py)
                   →  game.pgn

Run:  python pipeline_demo.py
"""

from validation_engine import validate_and_merge
from pgn_formatter import PGNFormatter, PGNHeaders

# ── Simulated Module 1 output (noisy OCR) ──────────────────────────────────
# Annotated with the OCR error and expected correction

WHITE_OCR = [
    {"move_number": 1,  "move_text": "e4",    "confidence": 0.97},  # OK
    {"move_number": 2,  "move_text": "Hf3",   "confidence": 0.71},  # Hf3 → Nf3
    {"move_number": 3,  "move_text": "Bb5",   "confidence": 0.93},  # OK
    {"move_number": 4,  "move_text": "Ba4",   "confidence": 0.88},  # OK
    {"move_number": 5,  "move_text": "0-0",   "confidence": 0.82},  # castling fix
    {"move_number": 6,  "move_text": "Re1",   "confidence": 0.90},  # OK
    {"move_number": 7,  "move_text": "Bb3",   "confidence": 0.85},  # OK
    {"move_number": 8,  "move_text": "c3",    "confidence": 0.95},  # OK
    {"move_number": 9,  "move_text": "h3",    "confidence": 0.88},  # OK
    {"move_number": 10, "move_text": "d4",    "confidence": 0.92},  # OK
]

BLACK_OCR = [
    {"move_number": 1,  "move_text": "e5",    "confidence": 0.96},  # OK
    {"move_number": 2,  "move_text": "Hc6",   "confidence": 0.68},  # Hc6 → Nc6
    {"move_number": 3,  "move_text": "a6",    "confidence": 0.91},  # OK
    {"move_number": 4,  "move_text": "Hf6",   "confidence": 0.70},  # Hf6 → Nf6
    {"move_number": 5,  "move_text": "Be7",   "confidence": 0.87},  # OK
    {"move_number": 6,  "move_text": "b5",    "confidence": 0.93},  # OK
    {"move_number": 7,  "move_text": "d6",    "confidence": 0.90},  # OK
    {"move_number": 8,  "move_text": "0-0",   "confidence": 0.80},  # castling fix
    {"move_number": 9,  "move_text": "Hb8",   "confidence": 0.55},  # Hb8 → Nb8
    # Move 10 intentionally missing (simulates torn scoresheet)
]


def main():
    print("═" * 60)
    print("  Chess Scoresheet → PGN   Full Pipeline Demo")
    print("═" * 60)

    # ── Module 2: Validate & Merge ──────────────────────────────────────
    print("\n▶  Module 2 – Validation & Merging …")
    game = validate_and_merge(WHITE_OCR, BLACK_OCR)

    print(f"\n   {game.summary()}")
    print(f"   Corrections : {len(game.corrected_moves)}")
    print(f"   Unknowns    : {len(game.unknown_moves)}")

    print("\n   Move log:")
    for m in game.moves:
        tag = ""
        if m.status.name != "OK":
            tag = f"  [{m.status.name}] {m.correction[:60]}"
        print(f"   {m.move_number:>3}. {m.side:<6}  {m.san:<10}{tag}")

    if game.flags:
        print("\n   Pipeline Flags:")
        for f in game.flags:
            print(f"   ⚑  {f}")

    # ── Persist validated game ──────────────────────────────────────────
    game.to_json("output/validated_game.json")

    # ── Module 3: PGN Formatting ────────────────────────────────────────
    print("\n▶  Module 3 – PGN Formatting …\n")

    headers = PGNHeaders.today(
        event="Ruy Lopez Training Game",
        site="Chennai Chess Academy",
        round="1",
        white="Arjun, V.",
        black="Priya, S.",
        result="*",
        extra={
            "ECO":       "C78",
            "Annotator": "ChessOCR Pipeline v1.0",
        },
    )

    formatter = PGNFormatter(
        headers,
        annotate_corrections=True,
        annotate_low_confidence=True,
        line_width=79,
    )

    formatter.save(game, "output/game.pgn")

    # ── Preview ─────────────────────────────────────────────────────────
    from pathlib import Path
    pgn_text = Path("output/game.pgn").read_text(encoding="utf-8")
    print("\n── PGN Output ─────────────────────────────────────────────")
    print(pgn_text)
    print("═" * 60)


if __name__ == "__main__":
    main()
