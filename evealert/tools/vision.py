import logging
from typing import List, Optional, Sequence, Tuple

import cv2 as cv
import numpy as np

from evealert.constants import (
    CV_DETECTION_COLOR,
    CV_LINE_TYPE,
    CV_RECTANGLE_THICKNESS,
    DETECTION_MAX_CANDIDATES,
    DETECTION_NMS_OVERLAP,
    DETECTION_THRESHOLD_MAX,
    DETECTION_THRESHOLD_MIN,
)
from evealert.exceptions import RegionSizeError, ScreenshotError

logger = logging.getLogger("tools")

Point = Tuple[int, int]


def _prepare_image(img: np.ndarray) -> np.ndarray:
    """Convert an image to a contiguous 3-channel uint8 BGR array."""
    if img.ndim == 2:
        img = cv.cvtColor(img, cv.COLOR_GRAY2BGR)
    elif img.shape[-1] == 4:
        img = cv.cvtColor(img, cv.COLOR_BGRA2BGR)
    if img.dtype != np.uint8:
        img = np.clip(img, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(img)


def _threshold_from_scale(threshold: float) -> float:
    """Convert a 0-100 detection scale into a clamped matching threshold."""
    return max(
        min(threshold / 100, DETECTION_THRESHOLD_MAX),
        DETECTION_THRESHOLD_MIN,
    )


def _non_max_suppression(
    boxes: np.ndarray, scores: np.ndarray, overlap: float
) -> List[np.ndarray]:
    """Keep the best-scoring boxes and drop boxes overlapping them.

    Args:
        boxes: Array of shape (N, 4) with x, y, w, h
        scores: Array of shape (N,) with match scores
        overlap: Maximum allowed intersection-over-union between kept boxes

    Returns:
        List of kept boxes (x, y, w, h)
    """
    if len(boxes) == 0:
        return []

    x1 = boxes[:, 0].astype(np.float32)
    y1 = boxes[:, 1].astype(np.float32)
    x2 = x1 + boxes[:, 2]
    y2 = y1 + boxes[:, 3]
    areas = boxes[:, 2].astype(np.float32) * boxes[:, 3]

    order = np.argsort(scores)[::-1]
    kept = []
    while order.size:
        best = order[0]
        kept.append(boxes[best])
        rest = order[1:]
        inter_w = np.clip(
            np.minimum(x2[best], x2[rest]) - np.maximum(x1[best], x1[rest]), 0, None
        )
        inter_h = np.clip(
            np.minimum(y2[best], y2[rest]) - np.maximum(y1[best], y1[rest]), 0, None
        )
        inter = inter_w * inter_h
        iou = inter / (areas[best] + areas[rest] - inter)
        order = rest[iou <= overlap]
    return kept


class Vision:
    """Computer vision handler for EVE Online UI element detection.

    Uses OpenCV template matching to detect enemy players and faction spawns
    in EVE Online screenshots. Supports multiple template images and various
    UI scaling factors.

    Template images are loaded and converted once, so each detection only
    runs the matching itself.

    Attributes:
        needle_imgs: List of prepared template images (BGR, uint8)
        needle_dims: Dimensions (width, height) of each template image
        method: OpenCV template matching method
        debug_mode: Show enemy detection visualization
        debug_mode_faction: Show faction detection visualization
    """

    def __init__(
        self, needle_img_paths: Sequence[str], method: int = cv.TM_CCOEFF_NORMED
    ):
        """Initialize the Vision handler.

        Args:
            needle_img_paths: List of paths to template images
            method: OpenCV template matching method (default: TM_CCOEFF_NORMED)
        """
        self.needle_imgs: List[np.ndarray] = []
        self.needle_paths: List[str] = []
        for path in needle_img_paths:
            img = cv.imread(path, cv.IMREAD_UNCHANGED)
            if img is None:
                logger.warning("Template image could not be loaded: %s", path)
                continue
            self.needle_imgs.append(_prepare_image(img))
            self.needle_paths.append(path)

        self.needle_dims = [(img.shape[1], img.shape[0]) for img in self.needle_imgs]
        # Correlation is undefined for single-colour templates (OpenCV then
        # reports a perfect match on every flat area of the screen), so those
        # are compared by colour difference instead.
        self.needle_flat = [
            bool(np.all(img.min(axis=(0, 1)) == img.max(axis=(0, 1))))
            for img in self.needle_imgs
        ]
        self.max_needle_w = max((w for w, _ in self.needle_dims), default=0)
        self.max_needle_h = max((h for _, h in self.needle_dims), default=0)

        self.method = method
        self.debug_mode = False
        self.debug_mode_faction = False
        # Names of the debug windows currently shown by this instance
        self._open_windows = set()

    @property
    def is_vision_open(self) -> bool:
        """Returns True if the enemy vision window is enabled."""
        return self.debug_mode

    @property
    def is_faction_vision_open(self) -> bool:
        """Returns True if the faction vision window is enabled."""
        return self.debug_mode_faction

    @property
    def has_templates(self) -> bool:
        """Returns True if at least one template image was loaded."""
        return bool(self.needle_imgs)

    @staticmethod
    def window_name(vision_mode: str) -> str:
        """Return the debug window title for a vision mode."""
        return f"{vision_mode} Vision"

    def detect(
        self,
        haystack_img: np.ndarray,
        threshold: float = 50,
        vision_mode: str = "Enemy",
        annotate: bool = False,
    ) -> Tuple[List[Point], Optional[np.ndarray]]:
        """Find all templates in the given image.

        Args:
            haystack_img: Screenshot to search in
            threshold: Detection scale in percent (0-100)
            vision_mode: "Enemy" or "Faction", used in messages
            annotate: Draw detection boxes on a copy of the image

        Returns:
            Tuple of (center points, image). The image is the annotated copy
            when ``annotate`` is True, otherwise the prepared input image.

        Raises:
            ScreenshotError: The image is missing or matching failed
            RegionSizeError: The region is smaller than a template image
        """
        if haystack_img is None or getattr(haystack_img, "size", 0) == 0:
            raise ScreenshotError(f"Detection {vision_mode} Error: No image captured.")

        try:
            haystack = _prepare_image(np.asarray(haystack_img))
        except cv.error as e:
            raise ScreenshotError(
                f"Detection {vision_mode} Error: Unsupported image format."
            ) from e

        if haystack.shape[0] < self.max_needle_h or haystack.shape[1] < self.max_needle_w:
            raise RegionSizeError(
                f"Detection {vision_mode} Error: Region is smaller than Detection Region please make a larger Area."
            )

        detection_threshold = _threshold_from_scale(threshold)
        all_boxes = []
        all_scores = []

        for idx, (needle_img, (needle_w, needle_h), flat) in enumerate(
            zip(self.needle_imgs, self.needle_dims, self.needle_flat)
        ):
            try:
                if flat:
                    result = self._match_flat(haystack, needle_img)
                else:
                    result = cv.matchTemplate(haystack, needle_img, self.method)
            except cv.error as e:
                logger.error("Detection %s Error (template %s): %s", vision_mode, idx, e)
                raise ScreenshotError(
                    f"Detection {vision_mode} Error: Something went wrong"
                ) from e

            ys, xs = np.nonzero(result >= detection_threshold)
            if xs.size == 0:
                continue

            scores = result[ys, xs]
            # A very low threshold can match nearly every pixel. Keep only the
            # best candidates so grouping stays fast.
            if scores.size > DETECTION_MAX_CANDIDATES:
                best = np.argpartition(scores, -DETECTION_MAX_CANDIDATES)[
                    -DETECTION_MAX_CANDIDATES:
                ]
                xs, ys, scores = xs[best], ys[best], scores[best]

            logger.debug(
                "Detection %s: template %s has %s candidates",
                vision_mode,
                idx,
                scores.size,
            )
            boxes = np.column_stack(
                (
                    xs,
                    ys,
                    np.full_like(xs, needle_w),
                    np.full_like(xs, needle_h),
                )
            )
            all_boxes.append(boxes)
            all_scores.append(scores)

        if not all_boxes:
            return [], haystack

        # Group across all templates so a 90% and 100% variant of the same
        # icon count as one detection.
        kept = _non_max_suppression(
            np.concatenate(all_boxes),
            np.concatenate(all_scores),
            DETECTION_NMS_OVERLAP,
        )

        points = [(int(x + w // 2), int(y + h // 2)) for x, y, w, h in kept]
        points.sort(key=lambda p: (p[1], p[0]))

        if annotate:
            haystack = haystack.copy()
            for x, y, w, h in kept:
                cv.rectangle(
                    haystack,
                    (int(x), int(y)),
                    (int(x + w), int(y + h)),
                    color=CV_DETECTION_COLOR,
                    lineType=CV_LINE_TYPE,
                    thickness=CV_RECTANGLE_THICKNESS,
                )

        return points, haystack

    @staticmethod
    def _match_flat(haystack: np.ndarray, needle_img: np.ndarray) -> np.ndarray:
        """Similarity (0-1) for a single-colour template based on colour distance."""
        sqdiff = cv.matchTemplate(
            haystack.astype(np.float32), needle_img.astype(np.float32), cv.TM_SQDIFF
        )
        rms = np.sqrt(np.maximum(sqdiff, 0) / needle_img.size)
        return 1.0 - rms / 255.0

    def vision_process(
        self, haystack_img, threshold: float = 50, vision_mode: str = "Enemy"
    ) -> tuple:
        """Backwards compatible wrapper around :meth:`detect`."""
        annotate = self.debug_mode or self.debug_mode_faction
        return self.detect(haystack_img, threshold, vision_mode, annotate)

    def _safe_destroy_window(self, name: str) -> None:
        """Destroy a debug window, ignoring backends without GUI support."""
        try:
            cv.destroyWindow(name)
        except cv.error as e:
            logger.debug("Could not destroy window %s: %s", name, e)
        self._open_windows.discard(name)

    def show_debug_window(self, vision_mode: str, image: np.ndarray) -> None:
        """Show (or refresh) the debug window for a vision mode.

        Must be called from the thread that runs the detection loop.
        """
        name = self.window_name(vision_mode)
        try:
            cv.imshow(name, image)
            cv.waitKey(1)
            self._open_windows.add(name)
        except cv.error as e:
            logger.error("Could not show %s: %s", name, e)

    def close_debug_window(self, vision_mode: str) -> None:
        """Close the debug window for a vision mode if it is open."""
        name = self.window_name(vision_mode)
        if name in self._open_windows:
            self._safe_destroy_window(name)

    def clean_up(self) -> None:
        """Close all open windows."""
        try:
            cv.destroyAllWindows()
        except cv.error as e:
            logger.debug("Could not destroy windows: %s", e)
        self._open_windows.clear()
        self.debug_mode = False
        self.debug_mode_faction = False

    def destroy_vision(self, vision_mode: str = "Enemy") -> None:
        """Disable and close the vision window."""
        if vision_mode == "Enemy":
            self.debug_mode = False
        elif vision_mode == "Faction":
            self.debug_mode_faction = False
        self._safe_destroy_window(self.window_name(vision_mode))

    def _find(self, haystack_img, threshold: float, vision_mode: str, show: bool) -> list:
        try:
            points, image = self.detect(haystack_img, threshold, vision_mode, show)
        except (ScreenshotError, RegionSizeError) as e:
            logger.error("%s Detection Error: %s", vision_mode, e)
            self.destroy_vision(vision_mode)
            return []

        if show:
            self.show_debug_window(vision_mode, image)
        else:
            self.close_debug_window(vision_mode)
        return points

    def find(self, haystack_img, threshold: float = 50) -> list:
        """Detect enemies and update the enemy debug window.

        Errors are logged and an empty list is returned.
        """
        return self._find(haystack_img, threshold, "Enemy", self.debug_mode)

    def find_faction(self, haystack_img, threshold: float = 50) -> list:
        """Detect faction spawns and update the faction debug window.

        Errors are logged and an empty list is returned.
        """
        return self._find(haystack_img, threshold, "Faction", self.debug_mode_faction)
