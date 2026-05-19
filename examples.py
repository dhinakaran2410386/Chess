"""
Example usage of the PGN Formatter module

This file demonstrates various use cases for the professional PGN formatter.
"""

from pgn_formatter import PGNFormatter


def example_1_basic_game():
    """Basic example: Create and export a simple chess game."""
    print("\n" + "="*70)
    print("EXAMPLE 1: Basic Game Export")
    print("="*70)
    
    pgn = PGNFormatter()
    
    # Create header
    pgn.create_header(
        event="World Chess Championship",
        site="New York, USA",
        date="2026.05.19",
        round_number="1",
        white_player="Garry Kasparov",
        black_player="Magnus Carlsen",
        result="1-0"
    )
    
    # Add moves
    moves = [
        'e4', 'e5',
        'Nf3', 'Nc6',
        'Bc4', 'Nf6',
        'Ng5', 'd5',
        'exd5', 'Nxd5',
        'Nxf7', 'Kxf7',
        'Qh5+', 'Kf8'
    ]
    pgn.add_moves(moves)
    
    # Display and export
    print("\nGenerated PGN:")
    print(pgn.generate_pgn())
    
    return pgn


def example_2_with_supplemental_tags():
    """Example with supplemental tags (ECO, Opening, etc.)"""
    print("\n" + "="*70)
    print("EXAMPLE 2: Game with Supplemental Tags")
    print("="*70)
    
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
    
    # Add supplemental tags
    pgn.add_supplemental_tags({
        'TimeControl': '7200+30',
        'ECO': 'D37',
        'Opening': 'Queen\'s Gambit Declined',
        'PlyCount': '58',
        'Annotator': 'Garry Kasparov',
        'Variant': 'Standard'
    })
    
    # Complete game moves (Queen's Gambit Declined example)
    moves = [
        'd4', 'd5',
        'c4', 'e6',
        'Nc3', 'Nf6',
        'Cxd5', 'exd5',
        'Nf3', 'Nc6',
        'g3', 'Be7',
        'Bg2', 'O-O',
        'O-O', 'Bf5',
        'Ne5', 'Nxe5',
        'dxe5', 'Ne4'
    ]
    pgn.add_moves(moves)
    
    print("\nGenerated PGN with Supplemental Tags:")
    print(pgn.generate_pgn())
    
    return pgn


def example_3_batch_processing():
    """Example: Process multiple games in batch."""
    print("\n" + "="*70)
    print("EXAMPLE 3: Batch Processing Multiple Games")
    print("="*70)
    
    games_data = [
        {
            'event': 'Tournament Round 1',
            'white': 'Alice Smith',
            'black': 'Bob Johnson',
            'moves': ['e4', 'e5', 'Nf3', 'Nc6', 'Bc4', 'Bc5'],
            'result': '1-0',
            'eco': 'C25'
        },
        {
            'event': 'Tournament Round 1',
            'white': 'Carol White',
            'black': 'David Brown',
            'moves': ['d4', 'd5', 'c4', 'e6', 'Nc3', 'Nf6', 'Bg5'],
            'result': '1/2-1/2',
            'eco': 'D30'
        },
        {
            'event': 'Tournament Round 1',
            'white': 'Eve Davis',
            'black': 'Frank Green',
            'moves': ['c4', 'e5', 'Nf3', 'Nc6', 'Nc3', 'Nf6'],
            'result': '0-1',
            'eco': 'A25'
        }
    ]
    
    pgn_games = []
    
    for i, game in enumerate(games_data, 1):
        pgn = PGNFormatter()
        
        pgn.create_header(
            event=game['event'],
            site="Tournament Hall, Chicago",
            date="2026.05.19",
            round_number=str(i),
            white_player=game['white'],
            black_player=game['black'],
            result=game['result']
        )
        
        pgn.add_supplemental_tags({
            'ECO': game['eco'],
            'TimeControl': '900+10'
        })
        
        pgn.add_moves(game['moves'])
        pgn_games.append(pgn)
        
        print(f"\nGame {i}: {game['white']} vs {game['black']}")
        print(f"Result: {game['result']}")
        print(pgn.format_moves())
    
    return pgn_games


def example_4_date_handling():
    """Example: Handle various date formats."""
    print("\n" + "="*70)
    print("EXAMPLE 4: Date Format Handling")
    print("="*70)
    
    dates_to_test = [
        ("2026.05.19", "Known date"),
        ("????.??.??", "Completely unknown date"),
        ("2026.05.??", "Unknown day"),
        ("????.12.25", "Unknown year and month"),
    ]
    
    for date, description in dates_to_test:
        pgn = PGNFormatter()
        try:
            pgn.create_header(
                event="Test Event",
                site="Test Site",
                date=date,
                round_number="1",
                white_player="Player A",
                black_player="Player B",
                result="*"
            )
            pgn.add_moves(['e4', 'e5'])
            print(f"\n✓ {description:20s} ({date}): Valid")
        except ValueError as e:
            print(f"\n✗ {description:20s} ({date}): Invalid - {e}")


def example_5_error_handling():
    """Example: Demonstrate error handling and validation."""
    print("\n" + "="*70)
    print("EXAMPLE 5: Error Handling and Validation")
    print("="*70)
    
    test_cases = [
        {
            'name': 'Invalid result',
            'params': {
                'event': 'Test', 'site': 'Test', 'date': '2026.05.19',
                'round_number': '1', 'white_player': 'A', 'black_player': 'B',
                'result': '2-0'  # Invalid!
            }
        },
        {
            'name': 'Invalid date format',
            'params': {
                'event': 'Test', 'site': 'Test', 'date': '05-19-2026',  # Wrong format!
                'round_number': '1', 'white_player': 'A', 'black_player': 'B',
                'result': '1-0'
            }
        },
        {
            'name': 'Empty moves list',
            'params': {
                'event': 'Test', 'site': 'Test', 'date': '2026.05.19',
                'round_number': '1', 'white_player': 'A', 'black_player': 'B',
                'result': '1-0'
            },
            'moves': []  # Empty!
        }
    ]
    
    for test in test_cases:
        pgn = PGNFormatter()
        print(f"\nTest: {test['name']}")
        
        try:
            pgn.create_header(**test['params'])
            
            if 'moves' in test:
                if test['moves']:  # Only if moves provided and not empty
                    pgn.add_moves(test['moves'])
                else:
                    pgn.add_moves(['e4', 'e5'])  # Add valid moves for test
                    pgn.add_moves([])  # Then try with empty - will raise error
            
            pgn.generate_pgn()
            print("✗ Expected error but succeeded!")
        
        except ValueError as e:
            print(f"✓ Caught expected error: {e}")


def example_6_create_from_file():
    """Example: Read moves from file and create PGN."""
    print("\n" + "="*70)
    print("EXAMPLE 6: Creating PGN from Validated Moves")
    print("="*70)
    
    # Simulating moves from a validated source (e.g., from chess engine or database)
    validated_moves_from_source = [
        'e4', 'c5',  # Sicilian Defense
        'Nf3', 'd6',
        'd4', 'cxd4',
        'Nxd4', 'Nf6',
        'Nc3', 'a6',
        'Bg5', 'e6',
        'f4', 'Be7'
    ]
    
    pgn = PGNFormatter()
    
    pgn.create_header(
        event="Sicilian Championship",
        site="Barcelona, Spain",
        date="2026.05.19",
        round_number="7",
        white_player="Anatoly Karpov",
        black_player="Viktor Korchnoi",
        result="*"  # Game still ongoing
    )
    
    pgn.add_supplemental_tags({
        'ECO': 'B94',
        'Opening': 'Sicilian Defense, Najdorf Variation'
    })
    
    pgn.add_moves(validated_moves_from_source)
    
    print("\nGenerated PGN from validated moves:")
    print(pgn.generate_pgn())
    
    return pgn


def main():
    """Run all examples."""
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  PGN FORMATTER - PROFESSIONAL EXAMPLES".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    example_1_basic_game()
    example_2_with_supplemental_tags()
    example_3_batch_processing()
    example_4_date_handling()
    example_5_error_handling()
    example_6_create_from_file()
    
    print("\n" + "█"*70)
    print("█" + "  All examples completed successfully!".center(68) + "█")
    print("█"*70 + "\n")


if __name__ == "__main__":
    main()
