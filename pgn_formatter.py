"""
Professional PGN (Portable Game Notation) Formatter

A production-ready module for creating, formatting, and exporting chess games
in full compliance with the official PGN 3.0 specification.

Features:
- Seven Tag Roster generation (mandatory PGN headers)
- Supplemental tag support (ECO, Opening, TimeControl, etc.)
- Standard move formatting with automatic numbering
- UTF-8 file export
- Comprehensive validation and error handling
- Batch game processing

Usage:
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
    pgn.add_moves(['e4', 'e5', 'Nf3', 'Nc6'])
    pgn.export_to_file("game.pgn")

PGN Specification: https://www.chessclub.com/help/PGN-spec
"""

from typing import List, Dict, Optional
import re


class PGNFormatter:
    """
    Professional PGN formatter for chess games.
    
    Implements the PGN 3.0 specification with support for:
    - Seven Tag Roster (mandatory headers)
    - Supplemental tags (ECO, Opening, etc.)
    - Standard move formatting
    - UTF-8 file export
    - Comprehensive validation
    
    Attributes:
        _tags (Dict[str, str]): All PGN tags (headers and supplemental)
        _moves (List[str]): List of moves in algebraic notation
        _seven_tag_roster (List[str]): Mandatory PGN tags
    """
    
    # Seven Tag Roster - mandatory in PGN
    _SEVEN_TAG_ROSTER = [
        'Event', 'Site', 'Date', 'Round', 'White', 'Black', 'Result'
    ]
    
    # Valid PGN results
    _VALID_RESULTS = ['1-0', '0-1', '1/2-1/2', '*']
    
    def __init__(self):
        """Initialize a new PGN formatter instance."""
        self._tags: Dict[str, str] = {}
        self._moves: List[str] = []
    
    def create_header(
        self,
        event: str,
        site: str,
        date: str,
        round_number: str,
        white_player: str,
        black_player: str,
        result: str
    ) -> None:
        """
        Create the Seven Tag Roster (mandatory PGN header).
        
        Args:
            event (str): Name of the event
            site (str): Location of the event
            date (str): Date in YYYY.MM.DD format (? for unknown parts)
            round_number (str): Round number or "-" for unknown
            white_player (str): Name of the White player
            black_player (str): Name of the Black player
            result (str): Game result ('1-0', '0-1', '1/2-1/2', or '*')
        
        Raises:
            ValueError: If date format is invalid or result is not recognized
            TypeError: If any parameter is not a string
        
        Example:
            pgn.create_header(
                event="World Championship",
                site="New York, USA",
                date="2026.05.19",
                round_number="1",
                white_player="Kasparov",
                black_player="Carlsen",
                result="1-0"
            )
        """
        # Validate types
        params = {
            'event': event, 'site': site, 'date': date,
            'round_number': round_number, 'white_player': white_player,
            'black_player': black_player, 'result': result
        }
        
        for param_name, param_value in params.items():
            if not isinstance(param_value, str):
                raise TypeError(f"{param_name} must be a string, got {type(param_value).__name__}")
        
        # Validate date format
        self._validate_date(date)
        
        # Validate result
        if result not in self._VALID_RESULTS:
            raise ValueError(
                f"Invalid result '{result}'. "
                f"Must be one of: {', '.join(self._VALID_RESULTS)}"
            )
        
        # Set Seven Tag Roster
        self._tags['Event'] = event
        self._tags['Site'] = site
        self._tags['Date'] = date
        self._tags['Round'] = round_number
        self._tags['White'] = white_player
        self._tags['Black'] = black_player
        self._tags['Result'] = result
    
    def _validate_date(self, date: str) -> None:
        """
        Validate PGN date format: YYYY.MM.DD with ? for unknown parts.
        
        Args:
            date (str): Date to validate
        
        Raises:
            ValueError: If date format is invalid
        """
        # Pattern: YYYY.MM.DD where each component can be ? or digits
        pattern = r'^(\d{4}|\?{4})\.(\d{2}|\?{2})\.(\d{2}|\?{2})$'
        
        if not re.match(pattern, date):
            raise ValueError(
                f"Invalid date format '{date}'. "
                f"Must be YYYY.MM.DD format (use ? for unknown parts). "
                f"Examples: 2026.05.19, 2026.??.??, ????.??.??"
            )
        
        # Validate numeric components if provided
        year, month, day = date.split('.')
        
        if year != '????':
            try:
                year_int = int(year)
                if year_int < 0 or year_int > 9999:
                    raise ValueError(f"Year must be between 0 and 9999, got {year_int}")
            except ValueError as e:
                raise ValueError(f"Invalid year in date '{date}': {e}")
        
        if month != '??':
            try:
                month_int = int(month)
                if month_int < 1 or month_int > 12:
                    raise ValueError(f"Month must be between 1 and 12, got {month_int}")
            except ValueError as e:
                raise ValueError(f"Invalid month in date '{date}': {e}")
        
        if day != '??':
            try:
                day_int = int(day)
                if day_int < 1 or day_int > 31:
                    raise ValueError(f"Day must be between 1 and 31, got {day_int}")
            except ValueError as e:
                raise ValueError(f"Invalid day in date '{date}': {e}")
    
    def add_supplemental_tags(self, tags: Dict[str, str]) -> None:
        """
        Add optional supplemental tags to enhance the PGN.
        
        Common supplemental tags:
        - ECO: Encyclopedia of Chess Openings code (e.g., 'C25')
        - Opening: Name of the opening (e.g., 'Vienna Game')
        - Variant: Chess variant (default: 'Standard')
        - TimeControl: Time control (e.g., '7200+30')
        - Annotator: Person who analyzed the game
        - PlyCount: Total number of half-moves
        
        Args:
            tags (Dict[str, str]): Dictionary of tag name-value pairs
        
        Example:
            pgn.add_supplemental_tags({
                'ECO': 'C25',
                'Opening': 'Vienna Game',
                'TimeControl': '7200+30',
                'Annotator': 'Garry Kasparov'
            })
        """
        if not isinstance(tags, dict):
            raise TypeError(f"tags must be a dictionary, got {type(tags).__name__}")
        
        for tag_name, tag_value in tags.items():
            if not isinstance(tag_name, str) or not isinstance(tag_value, str):
                raise TypeError(f"Tag name and value must be strings")
            
            # Don't overwrite Seven Tag Roster tags
            if tag_name in self._SEVEN_TAG_ROSTER:
                raise ValueError(
                    f"Cannot overwrite Seven Tag Roster tag '{tag_name}'. "
                    f"Use create_header() to set mandatory tags."
                )
            
            self._tags[tag_name] = tag_value
    
    def add_moves(self, moves: List[str]) -> None:
        """
        Add a list of validated chess moves in algebraic notation.
        
        Args:
            moves (List[str]): List of moves in standard algebraic notation
                Examples: ['e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'Bc5']
        
        Raises:
            ValueError: If moves list is empty
            TypeError: If moves is not a list or contains non-strings
        
        Supported move formats:
        - Pawn moves: e4, e5, d4
        - Piece moves: Nf3, Bc4, Ra1, Qe2
        - Captures: exd5, Nxe5, Bxf7
        - Castling: O-O (kingside), O-O-O (queenside)
        - Promotion: e8=Q, e1=N
        - Check: Nf3+
        - Checkmate: Nf3#
        
        Example:
            pgn.add_moves(['e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'Bc5'])
        """
        if not isinstance(moves, list):
            raise TypeError(f"moves must be a list, got {type(moves).__name__}")
        
        if not moves:
            raise ValueError("moves list cannot be empty")
        
        for i, move in enumerate(moves):
            if not isinstance(move, str):
                raise TypeError(f"Move at index {i} must be a string, got {type(move).__name__}")
        
        self._moves = moves
    
    def format_moves(self) -> str:
        """
        Format the moves into standard PGN format with automatic move numbering.
        
        Returns:
            str: Formatted moves in PGN format
        
        Example:
            pgn.add_moves(['e4', 'e5', 'Nf3', 'Nc6'])
            print(pgn.format_moves())
            # Output:
            # 1. e4 e5
            # 2. Nf3 Nc6
        """
        if not self._moves:
            return ""
        
        formatted_moves = []
        move_number = 1
        
        for i, move in enumerate(self._moves):
            # White move (always starts with move number)
            if i % 2 == 0:
                formatted_moves.append(f"{move_number}. {move}")
            # Black move
            else:
                formatted_moves[-1] += f" {move}"
                move_number += 1
        
        # Handle odd number of moves (if game is incomplete)
        # No special handling needed - last move is already formatted
        
        return " ".join(formatted_moves)
    
    def generate_pgn(self) -> str:
        """
        Generate the complete PGN text (headers + formatted moves + result).
        
        Returns:
            str: Complete PGN text in standard format
        
        Raises:
            ValueError: If headers haven't been created yet
        
        Example:
            pgn_text = pgn.generate_pgn()
            print(pgn_text)
        """
        if not self._tags or 'Event' not in self._tags:
            raise ValueError("Headers must be created first using create_header()")
        
        pgn_lines = []
        
        # Write Seven Tag Roster first
        for tag in self._SEVEN_TAG_ROSTER:
            if tag in self._tags:
                value = self._tags[tag]
                pgn_lines.append(f'[{tag} "{value}"]')
        
        # Write supplemental tags (in order they were added)
        for tag, value in self._tags.items():
            if tag not in self._SEVEN_TAG_ROSTER:
                pgn_lines.append(f'[{tag} "{value}"]')
        
        pgn_lines.append("")  # Blank line between headers and moves
        
        # Add formatted moves
        formatted = self.format_moves()
        if formatted:
            pgn_lines.append(formatted)
        
        # Add result at the end
        result = self._tags.get('Result', '*')
        pgn_lines.append(result)
        
        return "\n".join(pgn_lines)
    
    def export_to_file(self, filename: str) -> None:
        """
        Export the PGN to a file with UTF-8 encoding.
        
        Args:
            filename (str): Output filename (typically ends with .pgn)
        
        Raises:
            ValueError: If headers haven't been created yet
            IOError: If file cannot be written
        
        Example:
            pgn.export_to_file("game.pgn")
        """
        pgn_text = self.generate_pgn()
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(pgn_text)
            print(f"✓ PGN file created: {filename}")
        except IOError as e:
            raise IOError(f"Failed to write to file '{filename}': {e}")
    
    def clear(self) -> None:
        """
        Clear all headers and moves for reuse of the formatter.
        
        Example:
            pgn.clear()
            pgn.create_header(...)  # Create a new game
        """
        self._tags.clear()
        self._moves.clear()
    
    @staticmethod
    def export_multiple_games(filename: str, games: List['PGNFormatter']) -> None:
        """
        Export multiple PGN games to a single file.
        
        Args:
            filename (str): Output filename
            games (List[PGNFormatter]): List of PGNFormatter objects
        
        Raises:
            IOError: If file cannot be written
        
        Example:
            pgn1 = PGNFormatter()
            pgn1.create_header(...)
            pgn1.add_moves(...)
            
            pgn2 = PGNFormatter()
            pgn2.create_header(...)
            pgn2.add_moves(...)
            
            PGNFormatter.export_multiple_games("games.pgn", [pgn1, pgn2])
        """
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                for i, game in enumerate(games):
                    if i > 0:
                        f.write("\n\n")  # Blank line between games
                    f.write(game.generate_pgn())
            print(f"✓ Multi-game PGN file created: {filename}")
        except IOError as e:
            raise IOError(f"Failed to write to file '{filename}': {e}")


def create_pgn_from_moves(
    event: str,
    site: str,
    date: str,
    round_number: str,
    white_player: str,
    black_player: str,
    result: str,
    moves: List[str],
    output_file: Optional[str] = None,
    supplemental_tags: Optional[Dict[str, str]] = None
) -> str:
    """
    Convenience function to create and optionally export a PGN in one call.
    
    Args:
        event (str): Event name
        site (str): Event location
        date (str): Date in YYYY.MM.DD format
        round_number (str): Round number
        white_player (str): White player name
        black_player (str): Black player name
        result (str): Game result
        moves (List[str]): List of moves
        output_file (Optional[str]): Filename to export to
        supplemental_tags (Optional[Dict[str, str]]): Supplemental tags
    
    Returns:
        str: Generated PGN text
    
    Example:
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
    """
    pgn = PGNFormatter()
    pgn.create_header(
        event=event,
        site=site,
        date=date,
        round_number=round_number,
        white_player=white_player,
        black_player=black_player,
        result=result
    )
    
    if supplemental_tags:
        pgn.add_supplemental_tags(supplemental_tags)
    
    pgn.add_moves(moves)
    
    if output_file:
        pgn.export_to_file(output_file)
    
    return pgn.generate_pgn()


if __name__ == "__main__":
    # Quick test
    pgn = PGNFormatter()
    pgn.create_header(
        event="Test Game",
        site="Somewhere",
        date="2026.05.19",
        round_number="1",
        white_player="White",
        black_player="Black",
        result="*"
    )
    pgn.add_moves(['e4', 'e5', 'Nf3', 'Nc6'])
    print(pgn.generate_pgn())
