"""Reading the current solar system name from the screen.

The player selects (F3) the part of the EVE window that shows the name of the
current solar system. The alert worker reads that region with OCR and skips
enemy alarms while the player is in one of the systems entered in the
settings ("Nazwa systemu").

OCR is done by RapidOCR (ONNX models bundled with the package, no internet
access and no external programs needed). The engine is created on first use,
because loading the models takes about a second.

Matching is deliberately strict: a wrong match would silence real alarms, so
when anything goes wrong (no OCR engine, unreadable text, no match) the
alarms stay on.
"""

import re
import threading
from collections.abc import Iterable

import numpy as np

from evealert.settings.logger import logging

logger = logging.getLogger("tools")

# Characters OCR often confuses in EVE system names (1DQ1-A, O-IOAI, J123456).
# Both the read text and the names from the settings go through the same
# mapping, so "1DQ1-A" still matches when OCR reads "1D01-A".
_CONFUSABLE = str.maketrans(
    {
        "O": "0",
        "Q": "0",
        "I": "1",
        "L": "1",
        "|": "1",
        "!": "1",
        "S": "5",
        "B": "8",
        "Z": "2",
        "–": "-",  # en dash
        "—": "-",  # em dash
        "−": "-",  # minus sign
    }
)
_NOT_NAME_CHAR = re.compile(r"[^A-Z0-9\- ]+")
_SPACES = re.compile(r"\s+")
# Security status shown after the system name, e.g. "1.0", "-0.3" or "0. 5".
# OCR sometimes drops the space before it ("1DQ1-A-1.0").
_SECURITY = re.compile(r"\s?-?\d[.,]\s?\d\b.*$")

# Border (pixels) added around the region before OCR. The text detector
# misses text that touches the image edge; scaling the image up instead
# made the results worse in tests.
_OCR_PADDING = 16
# Text detector settings for small images (the defaults scale a 20 pixel
# high region up to 736 pixels, which takes over a second).
_OCR_OPTIONS = {"det_limit_type": "min", "det_limit_side_len": 64}
# A region image is treated as unchanged when the mean pixel difference is
# below this value, so OCR does not run again on every check.
_CHANGE_THRESHOLD = 2.0


def normalize(text: str) -> str:
    """Normalize text for comparing system names.

    Upper case, confusable characters mapped to digits, anything except
    letters, digits, "-" and single spaces removed.
    """
    text = (text or "").upper().translate(_CONFUSABLE)
    text = _NOT_NAME_CHAR.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def parse_names(value: str) -> list[str]:
    """Split the "Nazwa systemu" setting into names (comma or semicolon separated)."""
    names = []
    for part in re.split(r"[,;]", value or ""):
        part = part.strip()
        if part and part not in names:
            names.append(part)
    return names


def find_matching_name(text: str, names: Iterable[str]) -> str | None:
    """Return the first name from ``names`` that appears in the OCR ``text``.

    A name must appear as a whole word: "Jita" matches "Jita 1.0 < Kimotoro",
    but "Ala" does not match "Alamo".
    """
    normalized_text = normalize(text)
    if not normalized_text:
        return None
    for name in names:
        normalized_name = normalize(name)
        if not normalized_name:
            continue
        pattern = r"(?<![A-Z0-9])" + re.escape(normalized_name) + r"(?![A-Z0-9\-])"
        # OCR sometimes drops the space before the security status
        # ("Jita1.0", "1DQ1-A-1.0"; the dot is removed by normalize()), so
        # also accept a name followed directly by "<digit> <digit>".
        loose = (
            r"(?<![A-Z0-9])"
            + re.escape(normalized_name)
            + r"(?=-?[0-9] [0-9](?![A-Z0-9]))"
        )
        if re.search(pattern, normalized_text) or re.search(loose, normalized_text):
            return name
    return None


def extract_system_name(text: str) -> str:
    """Best guess of the system name in the OCR text (used in messages).

    The location panel shows "Jita 1.0 < Kimotoro < The Forge"; the name is
    the part before the security status and the "<" separators.
    """
    text = (text or "").strip()
    if not text:
        return ""
    text = re.split(r"[<>«»]", text, maxsplit=1)[0]
    text = _SECURITY.sub("", " " + text).strip()
    return _SPACES.sub(" ", text).strip(" .,-")


class SystemNameReader:
    """Reads text from a screen region with OCR.

    Thread-safe: OCR calls are serialized with a lock. The result for an
    unchanged image is cached.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._engine = None
        self._engine_error: str | None = None
        self._last_image: np.ndarray | None = None
        self._last_text = ""

    @property
    def error(self) -> str | None:
        """Reason why OCR is not available, or None."""
        return self._engine_error

    def _get_engine(self):
        if self._engine is None and self._engine_error is None:
            try:
                # pylint: disable=import-outside-toplevel
                from rapidocr_onnxruntime import RapidOCR

                try:
                    self._engine = RapidOCR(**_OCR_OPTIONS)
                except TypeError:
                    # Older RapidOCR versions do not take these options
                    self._engine = RapidOCR()
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("OCR engine could not be loaded: %s", e)
                self._engine_error = str(e) or e.__class__.__name__
        return self._engine

    def preload(self) -> bool:
        """Load the OCR models. Returns False if OCR is not available."""
        with self._lock:
            return self._get_engine() is not None

    def _is_unchanged(self, image: np.ndarray) -> bool:
        last = self._last_image
        if last is None or last.shape != image.shape:
            return False
        diff = np.abs(last.astype(np.int16) - image.astype(np.int16))
        return float(diff.mean()) < _CHANGE_THRESHOLD

    @staticmethod
    def _prepare(image: np.ndarray) -> np.ndarray:
        """Add a border in the background colour around the region."""
        # pylint: disable=import-outside-toplevel
        import cv2 as cv

        return cv.copyMakeBorder(
            np.ascontiguousarray(image),
            _OCR_PADDING,
            _OCR_PADDING,
            _OCR_PADDING,
            _OCR_PADDING,
            cv.BORDER_REPLICATE,
        )

    def read(self, image: np.ndarray | None, use_cache: bool = True) -> str | None:
        """Return the text found in ``image`` (BGR array).

        Returns:
            The text (lines joined with spaces; "" if nothing was found), or
            None if OCR is not available or failed.
        """
        if image is None or image.size == 0:
            return None
        with self._lock:
            if use_cache and self._is_unchanged(image):
                return self._last_text
            engine = self._get_engine()
            if engine is None:
                return None
            try:
                result, _ = engine(self._prepare(image))
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("OCR failed: %s", e)
                return None
            lines = []
            for item in result or []:
                # item: [box, text, score]
                try:
                    box, text = item[0], str(item[1]).strip()
                except (IndexError, TypeError):
                    continue
                if text:
                    top = min(point[1] for point in box) if box is not None else 0
                    lines.append((top, text))
            lines.sort(key=lambda line: line[0])
            text = " ".join(line[1] for line in lines)
            self._last_image = image.copy()
            self._last_text = text
            logger.debug("OCR read: %r", text)
            return text

    def reset(self) -> None:
        """Forget the cached result (e.g. after the region changed)."""
        with self._lock:
            self._last_image = None
            self._last_text = ""
