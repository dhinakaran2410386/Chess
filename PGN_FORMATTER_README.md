````markdown
# PGN Formatter - Professional Chess Game Notation

A production-ready Python module for creating, formatting, and exporting chess games in compliance with the official **PGN 3.0 specification**.

## 📋 Features

- ✅ **Seven Tag Roster** - Mandatory PGN headers (Event, Site, Date, Round, White, Black, Result)
- ✅ **Supplemental Tags** - Support for ECO, Opening, TimeControl, Annotator, and custom tags
- ✅ **Standard Move Formatting** - Automatic move numbering (1. e4 e5 2. Nf3 Nc6 ...)
- ✅ **UTF-8 File Export** - Proper encoding for all platforms
- ✅ **Comprehensive Validation** - Date format checking, result validation, type safety
- ✅ **Batch Processing** - Export multiple games to a single file
- ✅ **Professional Formatting** - Line wrapping, proper spacing, standard compliance

## 🚀 Quick Start

### Basic Usage

```python
from pgn_formatter import PGNFormatter

# Create formatter instance
pgn = PGNFormatter()

# Add header information
pgn.create_header(
    event="World Championship",
    site="New York, USA",
    date="2026.05.19",
    round_number="1",
    white_player="Kasparov",
    black_player="Carlsen",
    result="1-0"
)

# Add moves
pgn.add_moves(['e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'Bc5'])

# Export to file
pgn.export_to_file("game.pgn")
```

### Output Example

```
[Event "World Championship"]
[Site "New York, USA"]
[Date "2026.05.19"]
[Round "1"]
[White "Kasparov"]
[Black "Carlsen"]
[Result "1-0"]

1. e4 e5
2. Nf3 Nc6
3. Bc4 Bc5
1-0
```

## 📚 API Reference

### PGNFormatter Class

#### `__init__()`
Initializes a new PGN formatter instance.

```python
pgn = PGNFormatter()
```

---

#### `create_header()`
Creates the Seven Tag Roster (mandatory PGN header).

**Parameters:**
- `event` (str): Name of the event
- `site` (str): Location of the event
- `date` (str): Date in YYYY.MM.DD format (or ?.?.? for unknown parts)
- `round_number` (str): Round number or "-" for unknown
- `white_player` (str): Name of the White player
- `black_player` (str): Name of the Black player
- `result` (str): Game result ('1-0', '0-1', '1/2-1/2', or '*' for ongoing)

**Raises:**
- `ValueError`: If date format is invalid or result is not recognized
- `TypeError`: If any parameter is not a string

**Example:**
```python
pgn.create_header(
    event="London Chess Classic",
    site="London, England",
    date="2026.05.19",
    round_number="5",
    white_player="Ding Liren",
    black_player="Alireza Firouzja",
    result="0-1"
)
```

---

#### `add_supplemental_tags()`
Adds optional supplemental tags to enhance the PGN.

**Parameters:**
- `tags` (Dict[str, str]): Dictionary of tag name-value pairs

**Common Tags:**
| Tag | Example | Description |
|-----|---------|-------------|
| ECO | C25 | Encyclopedia of Chess Openings code |
| Opening | Vienna Game | Name of the opening |
| TimeControl | 7200+30 | Time control (seconds + increment) |
| Annotator | Garry Kasparov | Person who analyzed the game |
| PlyCount | 58 | Total number of half-moves |
| Variant | Standard | Chess variant (default: Standard) |

**Example:**
```python
pgn.add_supplemental_tags({
    'ECO': 'C25',
    'Opening': 'Vienna Game',
    'TimeControl': '7200+30',
    'Annotator': 'Garry Kasparov'
})
```

---

#### `add_moves()`
Adds a list of validated chess moves in algebraic notation.

**Parameters:**
- `moves` (List[str]): List of moves in standard algebraic notation (SAN)

**Raises:**
- `ValueError`: If moves list is empty
- `TypeError`: If moves is not a list or contains non-strings

**Move Examples:**
- Pawn moves: `e4`, `e5`, `d4`, `d5`
- Piece moves: `Nf3`, `Bc4`, `Ra1`, `Qe2`
- Captures: `exd5`, `Nxe5`, `Bxf7`
- Castling: `O-O` (kingside), `O-O-O` (queenside)
- Promotion: `e8=Q`, `e1=N`, `a8=R`
- Check: `Nf3+`
- Checkmate: `Nf3#`

**Example:**
```python
pgn.add_moves([
    'e4', 'e5',
    'Nf3', 'Nc6',
    'Bc4', 'Bc5',
    'Ng5', 'd5'
])
```

---

#### `format_moves()`
Formats the moves into standard PGN format with automatic move numbering.

**Returns:**
- str: Formatted moves

**Example:**
```python
pgn.add_moves(['e4', 'e5', 'Nf3', 'Nc6'])
print(pgn.format_moves())
# Output:
# 1. e4 e5
# 2. Nf3 Nc6
```

---

#### `generate_pgn()`
Generates the complete PGN text (headers + formatted moves).

**Returns:**
- str: Complete PGN text

**Raises:**
- `ValueError`: If headers haven't been created yet

**Example:**
```python
pgn_text = pgn.generate_pgn()
print(pgn_text)
```

---

#### `export_to_file()`
Exports the PGN to a file with UTF-8 encoding.

**Parameters:**
- `filename` (str): Output filename (should end with .pgn)

**Raises:**
- `ValueError`: If headers haven't been created yet
- `IOError`: If file cannot be written

**Example:**
```python
pgn.export_to_file("game.pgn")
```

---

#### `export_multiple_games()`
Static method to export multiple PGN games to a single file.

**Parameters:**
- `filename` (str): Output filename
- `games` (List[PGNFormatter]): List of PGNFormatter objects

**Example:**
```python
pgn1 = PGNFormatter()
pgn1.create_header(...)
pgn1.add_moves(...)

pgn2 = PGNFormatter()
pgn2.create_header(...)
pgn2.add_moves(...)

PGNFormatter.export_multiple_games("games.pgn", [pgn1, pgn2])
```

---

#### `clear()`
Clears all headers and moves for reuse of the formatter.

**Example:**
```python
pgn.clear()
pgn.create_header(...)  # Create a new game
```

---

### Convenience Function

#### `create_pgn_from_moves()`
Quick function to create and optionally export a PGN in one call.

**Parameters:**
- Standard header parameters (event, site, date, etc.)
- `moves` (List[str]): List of moves
- `output_file` (Optional[str]): Filename to export to
- `supplemental_tags` (Optional[Dict[str, str]]): Supplemental tags

**Returns:**
- str: Generated PGN text

**Example:**
```python
pgn_text = create_pgn_from_moves(
    event="Championship",
    site="New York, USA",
    date="2026.05.19",
    round_number="1",
    white_player="Player A",
    black_player="Player B",
    result="1-0",
    moves=['e4', 'e5', 'Nf3', 'Nc6'],
    output_file="game.pgn",
    supplemental_tags={'ECO': 'C25'}
)
```

---

## 📖 Usage Examples

### Example 1: Basic Game

```python
from pgn_formatter import PGNFormatter

pgn = PGNFormatter()
pgn.create_header(
    event="World Championship",
    site="New York, USA",
    date="2026.05.19",
    round_number="1",
    white_player="Kasparov",
    black_player="Carlsen",
    result="1-0"
)
pgn.add_moves(['e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'Bc5'])
pgn.export_to_file("game.pgn")
```

### Example 2: Game with Annotations

```python
pgn = PGNFormatter()
pgn.create_header(
    event="London Chess Classic",
    site="London, England",
    date="2026.05.19",
    round_number="5",
    white_player="Ding Liren",
    black_player="Alireza Firouzja",
    result="0-1"
)

pgn.add_supplemental_tags({
    'TimeControl': '7200+30',
    'ECO': 'D37',
    'Opening': 'Queen\'s Gambit Declined',
    'Annotator': 'Garry Kasparov'
})

pgn.add_moves([
    'd4', 'd5', 'c4', 'e6', 'Nc3', 'Nf6',
    'Cxd5', 'exd5', 'Nf3', 'Nc6', 'g3', 'Be7'
])

pgn.export_to_file("classical_game.pgn")
```

### Example 3: Batch Processing Tournament Games

```python
games_data = [
    {
        'white': 'Alice Smith',
        'black': 'Bob Johnson',
        'moves': ['e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'Bc5'],
        'result': '1-0'
    },
    {
        'white': 'Carol White',
        'black': 'David Brown',
        'moves': ['d4', 'd5', 'c4', 'e6', 'Nc3', 'Nf6'],
        'result': '1/2-1/2'
    }
]

games = []
for i, game_data in enumerate(games_data, 1):
    pgn = PGNFormatter()
    pgn.create_header(
        event="Tournament",
        site="Hall A",
        date="2026.05.19",
        round_number=str(i),
        white_player=game_data['white'],
        black_player=game_data['black'],
        result=game_data['result']
    )
    pgn.add_moves(game_data['moves'])
    games.append(pgn)

# Export all games to one file
PGNFormatter.export_multiple_games("tournament.pgn", games)
```

### Example 4: Unknown Dates

```python
# Completely unknown date
pgn.create_header(
    event="Old Game",
    site="Unknown",
    date="????.??.??",
    round_number="-",
    white_player="Player A",
    black_player="Player B",
    result="*"
)

# Known year, unknown month and day
pgn.create_header(
    event="Historical",
    site="Europe",
    date="1850.??.??",
    round_number="-",
    white_player="Old Master",
    black_player="Another Master",
    result="1-0"
)

# Known year and month, unknown day
pgn.create_header(
    event="Partial Info",
    site="Somewhere",
    date="2026.05.??",
    round_number="?",
    white_player="Player X",
    black_player="Player Y",
    result="0-1"
)
```

---

## 🔍 Date Format

The PGN standard uses the following date format:

```
YYYY.MM.DD
```

Where:
- `YYYY` - 4-digit year
- `MM` - 2-digit month (01-12)
- `DD` - 2-digit day (01-31)

For unknown components, use `?`:

```
????.??.??  # Completely unknown
2026.05.??  # Known year and month
2026.??.??  # Known year only
```

---

## ✅ Valid Results

The following results are recognized by PGN:

| Result | Meaning |
|--------|---------|
| `1-0` | White won |
| `0-1` | Black won |
| `1/2-1/2` | Draw |
| `*` | Game ongoing/unknown result |

---

## 🐛 Error Handling

The module provides comprehensive error handling:

```python
from pgn_formatter import PGNFormatter

pgn = PGNFormatter()

# Invalid date format
try:
    pgn.create_header(
        event="Test",
        site="Test",
        date="05-19-2026",  # Wrong format!
        round_number="1",
        white_player="A",
        black_player="B",
        result="1-0"
    )
except ValueError as e:
    print(f"Error: {e}")

# Invalid result
try:
    pgn.create_header(
        event="Test",
        site="Test",
        date="2026.05.19",
        round_number="1",
        white_player="A",
        black_player="B",
        result="2-0"  # Invalid!
    )
except ValueError as e:
    print(f"Error: {e}")

# Empty moves list
try:
    pgn.add_moves([])
except ValueError as e:
    print(f"Error: {e}")
```

---

## 📋 PGN Standard Reference

This module implements the **PGN Specification v3.0**, which includes:

1. **Seven Tag Roster** (Mandatory)
   - Event
   - Site
   - Date
   - Round
   - White
   - Black
   - Result

2. **Supplemental Tags** (Optional)
   - ECO, Opening, Variant, TimeControl, Annotator, etc.
   - Custom user-defined tags

3. **Move Format**
   - Standard Algebraic Notation (SAN)
   - Automatic move numbering
   - Move grouping (White-Black pairs)

4. **File Format**
   - UTF-8 encoding
   - One game per section
   - Multiple games separated by blank lines

**Official PGN Specification:**
https://www.chessclub.com/help/PGN-spec

---

## 📦 Installation

Simply import the module:

```python
from pgn_formatter import PGNFormatter
```

---

## 📄 License

MIT License - Feel free to use in your projects

---

## 🤝 Contributing

Contributions are welcome! Please ensure:
- All code follows PEP 8 style guidelines
- Comprehensive error handling is maintained
- PGN standard compliance is preserved
- Documentation is updated with new features

---

## 📞 Support

For issues or questions:
1. Check the examples in `examples.py`
2. Review the API Reference above
3. Check the official PGN specification

````
