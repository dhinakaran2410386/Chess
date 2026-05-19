"""
Unit Tests – Chess Scoresheet OCR Pipeline
============================================
Run with:  python -m pytest test_pipeline.py -v
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from scoresheet_pipeline import (
    GridDetector,
    ImagePreprocessor,
    RawMove,
    ScoresheetExtractor,
    ZonalOCR,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────

def make_blank(h=400, w=300, color=255) -> np.ndarray:
    img = np.full((h, w, 3), color, dtype=np.uint8)
    return img


def make_grid_image(rows=10, h=400, w=300) -> np.ndarray:
    """Synthetic scoresheet with horizontal lines."""
    img = np.full((h, w), 255, dtype=np.uint8)
    step = h // rows
    for i in range(rows + 1):
        cv2.line(img, (0, i * step), (w, i * step), 0, 1)
    cv2.line(img, (0, 0), (0, h), 0, 1)
    cv2.line(img, (w - 1, 0), (w - 1, h), 0, 1)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


# ─── ImagePreprocessor ─────────────────────────────────────────────────────

class TestImagePreprocessor:

    def test_grayscale_input_passthrough(self):
        gray = np.full((100, 80), 200, dtype=np.uint8)
        proc = ImagePreprocessor(deskew=False)
        binary, display = proc.run(gray)
        assert binary.ndim == 2
        assert display.ndim == 3

    def test_bgr_input(self):
        bgr = make_blank()
        proc = ImagePreprocessor(deskew=False)
        binary, display = proc.run(bgr)
        assert binary.shape[:2] == bgr.shape[:2]

    def test_binary_values(self):
        img = make_blank()
        proc = ImagePreprocessor(deskew=False)
        binary, _ = proc.run(img)
        unique = set(binary.flatten().tolist())
        assert unique.issubset({0, 255})

    def test_empty_image_raises(self):
        proc = ImagePreprocessor()
        with pytest.raises(ValueError, match="empty"):
            proc.run(np.array([]))

    def test_invalid_dimensions_raises(self):
        proc = ImagePreprocessor()
        with pytest.raises(ValueError, match="dimensions"):
            proc.run(np.zeros((4, 4, 4, 4), dtype=np.uint8))

    def test_even_blur_kernel_raises(self):
        with pytest.raises(ValueError, match="odd"):
            ImagePreprocessor(blur_kernel=4)


# ─── GridDetector ──────────────────────────────────────────────────────────

class TestGridDetector:

    def test_detects_cells_in_grid_image(self):
        img  = make_grid_image(rows=8)
        proc = ImagePreprocessor(deskew=False)
        binary, display = proc.run(img)
        det  = GridDetector(min_line_length=30, debug=False)
        cells = det.detect_cells(binary, display, side="white")
        assert len(cells) > 0

    def test_cells_are_sorted_top_to_bottom(self):
        img  = make_grid_image(rows=5)
        proc = ImagePreprocessor(deskew=False)
        binary, display = proc.run(img)
        det   = GridDetector(min_line_length=30)
        cells = det.detect_cells(binary, display, side="white")
        ys = [c[1] for c in cells]
        assert ys == sorted(ys)

    def test_merge_close_deduplicates(self):
        det    = GridDetector()
        coords = [10, 11, 12, 50, 51, 100]
        merged = det._merge_close(coords, tolerance=5)
        assert merged == [10, 50, 100]

    def test_filter_removes_tiny_cells(self):
        det   = GridDetector(min_cell_h=20, min_cell_w=30)
        cells = [(0, 0, 10, 5), (0, 0, 50, 30)]
        filtered = det._filter_cells(cells)
        assert len(filtered) == 1
        assert filtered[0] == (0, 0, 50, 30)


# ─── ZonalOCR ──────────────────────────────────────────────────────────────

class TestZonalOCR:

    @pytest.fixture
    def mock_ocr(self):
        with patch("scoresheet_pipeline.TESSERACT_AVAILABLE", True), \
             patch("scoresheet_pipeline.pytesseract") as mock_tess:
            mock_tess.Output.DICT = "dict"
            mock_tess.image_to_data.return_value = {
                "text": ["e4", ""],
                "conf": [92, -1],
            }
            yield ZonalOCR(engine="tesseract")

    def test_read_cell_returns_text_and_confidence(self, mock_ocr):
        cell = np.full((40, 80, 3), 200, dtype=np.uint8)
        text, conf = mock_ocr.read_cell(cell)
        assert text == "e4"
        assert 0.0 <= conf <= 1.0

    def test_prepare_cell_upscales_small_image(self):
        tiny = np.full((10, 40), 200, dtype=np.uint8)
        result = ZonalOCR._prepare_cell(tiny)
        assert result.shape[0] >= 32

    def test_prepare_cell_adds_border(self):
        img    = np.full((40, 80), 200, dtype=np.uint8)
        result = ZonalOCR._prepare_cell(img)
        # Border of 8px each side → height = 40 + 16
        assert result.shape[0] == 56

    def test_unknown_engine_raises(self):
        with pytest.raises(ValueError, match="Unknown OCR engine"):
            ZonalOCR(engine="magicbox")


# ─── ScoresheetExtractor ───────────────────────────────────────────────────

class TestScoresheetExtractor:

    def _make_extractor_with_mock_ocr(self):
        with patch("scoresheet_pipeline.TESSERACT_AVAILABLE", True), \
             patch("scoresheet_pipeline.pytesseract") as mock_tess:
            mock_tess.Output.DICT = "dict"
            mock_tess.image_to_data.return_value = {
                "text": ["e4"], "conf": [90]
            }
            return ScoresheetExtractor(engine="tesseract", min_confidence=0.1)

    def test_merge_interleaves_correctly(self):
        white = [RawMove(i + 1, "white", f"w{i}") for i in range(3)]
        black = [RawMove(i + 1, "black", f"b{i}") for i in range(3)]
        merged = ScoresheetExtractor._merge(white, black)
        sides  = [m.side for m in merged]
        assert sides == ["white", "black", "white", "black", "white", "black"]

    def test_merge_uneven_lengths(self):
        white = [RawMove(1, "white", "e4"), RawMove(2, "white", "d4")]
        black = [RawMove(1, "black", "e5")]
        merged = ScoresheetExtractor._merge(white, black)
        assert len(merged) == 3

    def test_clean_move_text_castling(self):
        assert ScoresheetExtractor._clean_move_text("0-0") == "O-O"
        assert ScoresheetExtractor._clean_move_text("0-0-0") == "O-O-O"

    def test_clean_move_text_strips_whitespace(self):
        assert ScoresheetExtractor._clean_move_text("  Nf3 ") == "Nf3"

    def test_save_json(self, tmp_path):
        moves  = [RawMove(1, "white", "e4", 0.9), RawMove(1, "black", "e5", 0.85)]
        ext    = ScoresheetExtractor.__new__(ScoresheetExtractor)
        out    = str(tmp_path / "moves.json")
        ext.save_json(moves, out)
        data   = json.loads(Path(out).read_text())
        assert len(data) == 2
        assert data[0]["move_text"] == "e4"

    def test_save_csv(self, tmp_path):
        moves = [RawMove(1, "white", "e4", 0.9)]
        ext   = ScoresheetExtractor.__new__(ScoresheetExtractor)
        out   = str(tmp_path / "moves.csv")
        ext.save_csv(moves, out)
        content = Path(out).read_text()
        assert "move_number" in content
        assert "e4" in content

    def test_load_nonexistent_image_returns_none(self):
        result = ScoresheetExtractor._load_image("no_such_file.png", "white")
        assert result is None


# ─── RawMove ───────────────────────────────────────────────────────────────

class TestRawMove:

    def test_to_dict_excludes_bbox(self):
        m = RawMove(1, "white", "e4", 0.9, bbox=(0, 0, 50, 20))
        d = m.to_dict()
        assert "bbox" not in d

    def test_to_dict_fields(self):
        m = RawMove(3, "black", "Nf6", 0.8)
        d = m.to_dict()
        assert d == {
            "move_number": 3,
            "side": "black",
            "move_text": "Nf6",
            "confidence": 0.8,
        }
