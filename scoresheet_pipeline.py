"""
Chess Scoresheet OCR Pipeline
==============================
Preprocessing & Extraction Module

Converts images of handwritten/printed chess scoresheets into structured
move data (JSON/CSV), ready for downstream PGN assembly.

"""

from __future__ import annotations

import csv
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Optional OCR back-ends  (at least one must be installed)
# ---------------------------------------------------------------------------
try:
    import pytesseract                     # pip install pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import easyocr                         # pip install easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ===========================================================================
# Data Model
# ===========================================================================

@dataclass
class RawMove:
    """One extracted cell from the scoresheet."""
    move_number: int
    side: str          # "white" | "black"
    move_text: str
    confidence: float = 1.0
    bbox: Optional[Tuple[int, int, int, int]] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("bbox")          # not serialised to JSON/CSV
        return d


# ===========================================================================
# Image Preprocessing
# ===========================================================================

class ImagePreprocessor:
    """
    Converts a raw scoresheet image into a clean binary image and exposes
    helper utilities used by the grid detector.
    """

    def __init__(
        self,
        blur_kernel: int = 3,
        block_size: int = 31,
        c_constant: int = 10,
        morph_kernel: int = 3,
        deskew: bool = True,
    ) -> None:
        if blur_kernel % 2 == 0:
            raise ValueError("blur_kernel must be odd.")
        if block_size % 2 == 0:
            raise ValueError("block_size must be odd.")

        self.blur_kernel   = blur_kernel
        self.block_size    = block_size
        self.c_constant    = c_constant
        self.morph_kernel  = morph_kernel
        self.deskew        = deskew

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, image: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Full preprocessing chain.

        Returns
        -------
        binary   : thresholded image (uint8, values 0 / 255)
        display  : colour image after deskew (for debug overlays)
        """
        self._validate(image)

        gray = self._to_gray(image)

        if self.deskew:
            gray = self._correct_skew(gray)

        # Keep a colour copy for debug overlays
        display = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        blurred  = self._blur(gray)
        binary   = self._threshold(blurred)
        binary   = self._morphological_cleanup(binary)

        return binary, display

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(image: np.ndarray) -> None:
        if image is None or image.size == 0:
            raise ValueError("Received an empty or None image.")
        if image.ndim not in (2, 3):
            raise ValueError(f"Unexpected image dimensions: {image.ndim}")

    @staticmethod
    def _to_gray(image: np.ndarray) -> np.ndarray:
        if image.ndim == 3:
            log.debug("Converting BGR → Grayscale")
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return image.copy()

    def _blur(self, gray: np.ndarray) -> np.ndarray:
        k = self.blur_kernel
        log.debug("Gaussian blur  kernel=(%d,%d)", k, k)
        return cv2.GaussianBlur(gray, (k, k), sigmaX=0)

    def _threshold(self, blurred: np.ndarray) -> np.ndarray:
        """
        Two-pass thresholding:
          1. Otsu's method on the global image.
          2. Adaptive (Gaussian-weighted) for local contrast variation.
        The bitwise-AND of both gives the cleanest binary.
        """
        log.debug("Thresholding  (Otsu + Adaptive Gaussian)")

        # Pass 1 – Otsu
        _, otsu = cv2.threshold(
            blurred, 0, 255,
            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
        )

        # Pass 2 – Adaptive
        adaptive = cv2.adaptiveThreshold(
            blurred,
            maxValue=255,
            adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            thresholdType=cv2.THRESH_BINARY_INV,
            blockSize=self.block_size,
            C=self.c_constant,
        )

        # Combine: keep only pixels flagged by *both* methods
        combined = cv2.bitwise_and(otsu, adaptive)
        return combined

    def _morphological_cleanup(self, binary: np.ndarray) -> np.ndarray:
        k = self.morph_kernel
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
        # Remove tiny speckles
        cleaned = cv2.morphologyEx(binary, cv2.MORPH_OPEN,  kernel, iterations=1)
        # Close small gaps in strokes
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel, iterations=1)
        return cleaned

    @staticmethod
    def _correct_skew(gray: np.ndarray) -> np.ndarray:
        """
        Deskew using Hough line analysis on the longest horizontal lines.
        Falls back gracefully if angle cannot be determined.
        """
        edges  = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines  = cv2.HoughLines(edges, 1, np.pi / 180, threshold=200)

        if lines is None:
            log.debug("Skew correction: no lines found, skipping.")
            return gray

        angles = []
        for rho, theta in lines[:, 0]:
            angle = np.degrees(theta) - 90
            if abs(angle) < 15:          # ignore near-vertical lines
                angles.append(angle)

        if not angles:
            return gray

        median_angle = float(np.median(angles))
        log.debug("Deskew angle: %.2f°", median_angle)

        h, w = gray.shape
        M    = cv2.getRotationMatrix2D((w / 2, h / 2), median_angle, 1.0)
        return cv2.warpAffine(gray, M, (w, h),
                              flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)


# ===========================================================================
# Grid / Cell Detection
# ===========================================================================

class GridDetector:
    """
    Locates the table grid on the scoresheet and extracts individual cells.

    Strategy
    --------
    1. Detect long horizontal and vertical line segments (Hough Probabilistic).
    2. Find intersections → candidate cell corners.
    3. Cluster corners into a regular grid.
    4. Fall back to uniform-division if the grid is too noisy.
    """

    def __init__(
        self,
        min_line_length: int = 60,
        max_line_gap: int    = 10,
        min_cell_h: int      = 15,
        min_cell_w: int      = 20,
        debug: bool          = False,
    ) -> None:
        self.min_line_length = min_line_length
        self.max_line_gap    = max_line_gap
        self.min_cell_h      = min_cell_h
        self.min_cell_w      = min_cell_w
        self.debug           = debug

    # ------------------------------------------------------------------

    def detect_cells(
        self,
        binary: np.ndarray,
        display: np.ndarray,
        side: str,                     # "white" | "black"
    ) -> List[Tuple[int, int, int, int]]:
        """
        Returns a sorted list of (x, y, w, h) bounding boxes for each cell,
        ordered top-to-bottom (move 1 → move N).
        """
        h_lines, v_lines = self._find_lines(binary)

        if h_lines and v_lines:
            cells = self._cells_from_grid(h_lines, v_lines, binary.shape)
        else:
            log.warning(
                "[%s] Grid lines sparse – falling back to contour detection.",
                side,
            )
            cells = self._cells_from_contours(binary)

        cells = self._filter_cells(cells)
        cells = self._sort_cells(cells)

        if self.debug:
            self._draw_debug(display, cells, h_lines, v_lines)

        log.info("[%s] Detected %d cells.", side, len(cells))
        return cells

    # ------------------------------------------------------------------
    # Line Detection
    # ------------------------------------------------------------------

    def _find_lines(
        self, binary: np.ndarray
    ) -> Tuple[List[Tuple], List[Tuple]]:
        """Extract near-horizontal and near-vertical line segments."""
        edges = cv2.Canny(binary, 50, 150)
        raw   = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=80,
            minLineLength=self.min_line_length,
            maxLineGap=self.max_line_gap,
        )

        h_lines: List[Tuple] = []
        v_lines: List[Tuple] = []

        if raw is None:
            return h_lines, v_lines

        for x1, y1, x2, y2 in raw[:, 0]:
            angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            if angle < 10:          # horizontal  (±10°)
                h_lines.append((x1, y1, x2, y2))
            elif angle > 80:        # vertical    (80°–100°)
                v_lines.append((x1, y1, x2, y2))

        return h_lines, v_lines

    # ------------------------------------------------------------------
    # Cell extraction strategies
    # ------------------------------------------------------------------

    def _cells_from_grid(
        self,
        h_lines: List[Tuple],
        v_lines: List[Tuple],
        shape: Tuple[int, int],
    ) -> List[Tuple[int, int, int, int]]:
        """Build cells from intersecting H/V lines."""
        img_h, img_w = shape

        # Representative y-coords of horizontal lines
        y_coords = sorted({int(np.mean([y1, y2])) for x1, y1, x2, y2 in h_lines})
        x_coords = sorted({int(np.mean([x1, x2])) for x1, y1, x2, y2 in v_lines})

        y_coords = self._merge_close(y_coords, tolerance=10)
        x_coords = self._merge_close(x_coords, tolerance=10)

        cells: List[Tuple[int, int, int, int]] = []
        for i in range(len(y_coords) - 1):
            for j in range(len(x_coords) - 1):
                x = x_coords[j]
                y = y_coords[i]
                w = x_coords[j + 1] - x
                h = y_coords[i + 1] - y
                cells.append((x, y, w, h))

        return cells

    def _cells_from_contours(
        self, binary: np.ndarray
    ) -> List[Tuple[int, int, int, int]]:
        """Fallback: find closed contours that look like cells."""
        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        cells = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            aspect = w / max(h, 1)
            if 0.5 < aspect < 8.0:           # plausible cell shape
                cells.append((x, y, w, h))
        return cells

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_close(coords: List[int], tolerance: int) -> List[int]:
        """Cluster coordinates that are within `tolerance` pixels."""
        if not coords:
            return []
        merged = [coords[0]]
        for c in coords[1:]:
            if c - merged[-1] > tolerance:
                merged.append(c)
        return merged

    def _filter_cells(
        self, cells: List[Tuple[int, int, int, int]]
    ) -> List[Tuple[int, int, int, int]]:
        return [
            (x, y, w, h) for x, y, w, h in cells
            if h >= self.min_cell_h and w >= self.min_cell_w
        ]

    @staticmethod
    def _sort_cells(
        cells: List[Tuple[int, int, int, int]]
    ) -> List[Tuple[int, int, int, int]]:
        """Sort top-to-bottom, left-to-right."""
        return sorted(cells, key=lambda c: (c[1], c[0]))

    def _draw_debug(
        self,
        display: np.ndarray,
        cells: List[Tuple[int, int, int, int]],
        h_lines: List[Tuple],
        v_lines: List[Tuple],
    ) -> None:
        for x1, y1, x2, y2 in h_lines:
            cv2.line(display, (x1, y1), (x2, y2), (0, 255, 0), 1)
        for x1, y1, x2, y2 in v_lines:
            cv2.line(display, (x1, y1), (x2, y2), (255, 0, 0), 1)
        for i, (x, y, w, h) in enumerate(cells):
            cv2.rectangle(display, (x, y), (x + w, y + h), (0, 0, 255), 1)
            cv2.putText(display, str(i), (x + 2, y + 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)


# ===========================================================================
# Zonal OCR Engine
# ===========================================================================

class ZonalOCR:
    """
    Runs OCR on individual cropped cell images.

    Supports:
      - Tesseract (via pytesseract)
      - EasyOCR
    """

    TESSERACT_CONFIG = (
        "--psm 7 "                      # single text line
        "--oem 3 "                      # LSTM engine
        "-c tessedit_char_whitelist="
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789-+=#+O "
    )

    def __init__(self, engine: str = "tesseract") -> None:
        engine = engine.lower()
        if engine == "tesseract":
            if not TESSERACT_AVAILABLE:
                raise RuntimeError(
                    "pytesseract is not installed. "
                    "Run: pip install pytesseract"
                )
            self.engine = "tesseract"
            log.info("OCR engine: Tesseract")

        elif engine == "easyocr":
            if not EASYOCR_AVAILABLE:
                raise RuntimeError(
                    "easyocr is not installed. "
                    "Run: pip install easyocr"
                )
            self._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            self.engine  = "easyocr"
            log.info("OCR engine: EasyOCR")

        else:
            raise ValueError(f"Unknown OCR engine '{engine}'. Use 'tesseract' or 'easyocr'.")

    # ------------------------------------------------------------------

    def read_cell(self, cell_img: np.ndarray) -> Tuple[str, float]:
        """
        Parameters
        ----------
        cell_img : grayscale or BGR crop of one grid cell

        Returns
        -------
        (text, confidence)   confidence in [0, 1]
        """
        prepped = self._prepare_cell(cell_img)

        try:
            if self.engine == "tesseract":
                return self._tesseract(prepped)
            return self._easyocr(prepped)
        except Exception as exc:
            log.warning("OCR failed for cell: %s", exc)
            return "", 0.0

    # ------------------------------------------------------------------
    # Cell preparation
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare_cell(img: np.ndarray) -> np.ndarray:
        """
        Normalise a cell crop for best OCR accuracy:
          - Convert to grayscale if needed.
          - Add a white border (Tesseract performs better with padding).
          - Upscale small cells (< 32 px tall).
          - Apply light sharpening.
        """
        if img.ndim == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Upscale tiny cells
        h, w = img.shape
        if h < 32:
            scale = 32 / h
            img = cv2.resize(img, (int(w * scale), 32),
                             interpolation=cv2.INTER_CUBIC)

        # Sharpen
        kernel  = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        img     = cv2.filter2D(img, -1, kernel)

        # Add border
        img = cv2.copyMakeBorder(img, 8, 8, 8, 8,
                                 cv2.BORDER_CONSTANT, value=255)
        return img

    # ------------------------------------------------------------------
    # Engine-specific readers
    # ------------------------------------------------------------------

    def _tesseract(self, img: np.ndarray) -> Tuple[str, float]:
        data = pytesseract.image_to_data(
            img,
            config=self.TESSERACT_CONFIG,
            output_type=pytesseract.Output.DICT,
        )
        words  = []
        confs  = []
        for text, conf in zip(data["text"], data["conf"]):
            text = text.strip()
            if text and int(conf) > 0:
                words.append(text)
                confs.append(int(conf))

        raw_text  = " ".join(words).strip()
        avg_conf  = (sum(confs) / len(confs) / 100.0) if confs else 0.0
        return raw_text, avg_conf

    def _easyocr(self, img: np.ndarray) -> Tuple[str, float]:
        results = self._reader.readtext(img, detail=1)
        if not results:
            return "", 0.0
        texts  = [r[1] for r in results]
        confs  = [r[2] for r in results]
        return " ".join(texts).strip(), float(np.mean(confs))


# ===========================================================================
# Extraction Pipeline
# ===========================================================================

class ScoresheetExtractor:
    """
    Orchestrates the full extraction pipeline for one side of the scoresheet.

    Usage
    -----
    extractor = ScoresheetExtractor(engine="tesseract", debug=True)
    moves = extractor.extract(white_image_path, black_image_path)
    extractor.save_json(moves, "output/moves.json")
    extractor.save_csv(moves, "output/moves.csv")
    """

    def __init__(
        self,
        engine: str = "tesseract",
        min_confidence: float = 0.3,
        debug: bool = False,
        debug_dir: str = "debug_output",
    ) -> None:
        self.min_confidence = min_confidence
        self.debug          = debug
        self.debug_dir      = Path(debug_dir)

        self.preprocessor = ImagePreprocessor(deskew=True)
        self.grid_detector = GridDetector(debug=debug)
        self.ocr           = ZonalOCR(engine=engine)

        if debug:
            self.debug_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(
        self,
        white_image_path: str,
        black_image_path: str,
    ) -> List[RawMove]:
        """
        Extract moves from both scoresheet images and return a merged,
        move-number-sorted list of RawMove objects.
        """
        white_moves = self._process_side(white_image_path, side="white")
        black_moves = self._process_side(black_image_path, side="black")
        return self._merge(white_moves, black_moves)

    def save_json(self, moves: List[RawMove], path: str) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        data = [m.to_dict() for m in moves]
        with out.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        log.info("JSON saved → %s  (%d moves)", out, len(data))

    def save_csv(self, moves: List[RawMove], path: str) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        fields = ["move_number", "side", "move_text", "confidence"]
        with out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for m in moves:
                row = m.to_dict()
                row["confidence"] = f"{row['confidence']:.3f}"
                writer.writerow(row)
        log.info("CSV saved → %s  (%d rows)", out, len(moves))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _process_side(self, image_path: str, side: str) -> List[RawMove]:
        log.info("─── Processing [%s]  %s", side, image_path)

        image = self._load_image(image_path, side)
        if image is None:
            return []

        binary, display = self.preprocessor.run(image)
        cells           = self.grid_detector.detect_cells(binary, display, side)

        if not cells:
            log.error("[%s] No cells detected. Check image quality.", side)
            return []

        moves = self._ocr_cells(image, cells, side)

        if self.debug:
            dbg_path = self.debug_dir / f"debug_{side}.png"
            cv2.imwrite(str(dbg_path), display)
            log.debug("Debug image saved → %s", dbg_path)

        return moves

    @staticmethod
    def _load_image(path: str, side: str) -> Optional[np.ndarray]:
        img = cv2.imread(path)
        if img is None:
            log.error("[%s] Could not read image: %s", side, path)
        else:
            log.debug("[%s] Loaded  %s  shape=%s", side, path, img.shape)
        return img

    def _ocr_cells(
        self,
        image: np.ndarray,
        cells: List[Tuple[int, int, int, int]],
        side: str,
    ) -> List[RawMove]:
        moves: List[RawMove] = []
        h_img, w_img = image.shape[:2]

        for idx, (x, y, w, h) in enumerate(cells):
            # Guard against out-of-bounds crops
            x1, y1 = max(x, 0), max(y, 0)
            x2, y2 = min(x + w, w_img), min(y + h, h_img)

            if x2 <= x1 or y2 <= y1:
                log.debug("[%s] Cell %d has zero area, skipping.", side, idx)
                continue

            crop = image[y1:y2, x1:x2]
            text, conf = self.ocr.read_cell(crop)

            # Skip blank / low-confidence cells
            if not text or conf < self.min_confidence:
                log.debug(
                    "[%s] Cell %d rejected  text=%r  conf=%.2f",
                    side, idx, text, conf,
                )
                continue

            text = self._clean_move_text(text)
            if not text:
                continue

            moves.append(
                RawMove(
                    move_number=idx + 1,        # re-numbered after merge
                    side=side,
                    move_text=text,
                    confidence=conf,
                    bbox=(x1, y1, x2 - x1, y2 - y1),
                )
            )
            log.debug(
                "[%s] Cell %d → %r  (conf=%.2f)", side, idx, text, conf
            )

        log.info("[%s] Extracted %d valid moves.", side, len(moves))
        return moves

    @staticmethod
    def _clean_move_text(text: str) -> str:
        """
        Minimal normalisation – keeps valid chess notation characters.
        Replace common OCR misreads.
        """
        substitutions = {
            "0": "O",      # castling: 0-0 → O-O
            "l": "1",
            "|": "1",
        }
        cleaned = text.strip()
        for wrong, right in substitutions.items():
            cleaned = cleaned.replace(wrong, right)
        # Remove stray punctuation except chess-relevant ones
        cleaned = "".join(c for c in cleaned if c.isalnum() or c in "-+=#+Ox ")
        return cleaned.strip()

    @staticmethod
    def _merge(
        white: List[RawMove],
        black: List[RawMove],
    ) -> List[RawMove]:
        """
        Assign sequential move numbers.
        White cells → odd rows; Black cells → even rows (or interleaved).
        """
        combined: List[RawMove] = []

        # Re-number both sides sequentially from 1
        for i, m in enumerate(white):
            m.move_number = i + 1
        for i, m in enumerate(black):
            m.move_number = i + 1

        # Interleave: (w1, b1, w2, b2, …)
        max_len = max(len(white), len(black))
        for i in range(max_len):
            if i < len(white):
                combined.append(white[i])
            if i < len(black):
                combined.append(black[i])

        return combined


# ===========================================================================
# CLI Entry Point
# ===========================================================================

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Chess Scoresheet OCR – Preprocessing & Extraction Module",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("white_image",  help="Path to White's scoresheet image")
    parser.add_argument("black_image",  help="Path to Black's scoresheet image")
    parser.add_argument("--engine",     default="tesseract",
                        choices=["tesseract", "easyocr"],
                        help="OCR back-end")
    parser.add_argument("--out-json",   default="output/moves.json",
                        help="Output JSON file path")
    parser.add_argument("--out-csv",    default="output/moves.csv",
                        help="Output CSV file path")
    parser.add_argument("--min-conf",   type=float, default=0.3,
                        help="Minimum OCR confidence (0-1)")
    parser.add_argument("--debug",      action="store_true",
                        help="Save debug overlay images to ./debug_output/")
    parser.add_argument("--verbose",    action="store_true",
                        help="Enable DEBUG logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    extractor = ScoresheetExtractor(
        engine=args.engine,
        min_confidence=args.min_conf,
        debug=args.debug,
    )

    moves = extractor.extract(args.white_image, args.black_image)

    if not moves:
        log.error("No moves extracted. Exiting.")
        sys.exit(1)

    extractor.save_json(moves, args.out_json)
    extractor.save_csv(moves, args.out_csv)

    # Preview first 10 moves
    print("\n── Extracted Moves (preview) ─────────────────────")
    for m in moves[:10]:
        print(f"  Move {m.move_number:>3}  [{m.side:<5}]  "
              f"{m.move_text:<12}  conf={m.confidence:.2f}")
    if len(moves) > 10:
        print(f"  … and {len(moves) - 10} more.")


if __name__ == "__main__":
    main()
