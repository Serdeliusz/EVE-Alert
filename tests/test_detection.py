"""Tests for template preparation, grouping and screen capture."""

import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2 as cv
import numpy as np

from evealert.constants import DETECTION_MAX_CANDIDATES
from evealert.exceptions import RegionSizeError, ScreenshotError
from evealert.tools.vision import Vision, _non_max_suppression
from evealert.tools.windowscapture import WindowCapture

FIXTURES = Path("tests/fixtures_detection")


def _icon(size: int = 12) -> np.ndarray:
    """Create a small icon with structure (like the EVE standing icons)."""
    icon = np.full((size, size, 3), 110, dtype=np.uint8)
    icon[3:5, 3 : size - 3] = 255
    icon[size - 5 : size - 3, 3 : size - 3] = 255
    icon[0, :] = 140
    icon[:, 0] = 140
    return icon


class DetectionTests(unittest.TestCase):
    """Detection behaviour of the Vision class."""

    def setUp(self):
        FIXTURES.mkdir(parents=True, exist_ok=True)
        self.icon = _icon()
        self.icon_path = FIXTURES / "icon.png"
        cv.imwrite(str(self.icon_path), self.icon)

        # Same icon with an alpha channel, like image_1_90%.png
        bgra = cv.cvtColor(self.icon, cv.COLOR_BGR2BGRA)
        self.icon_alpha_path = FIXTURES / "icon_alpha.png"
        cv.imwrite(str(self.icon_alpha_path), bgra)

    def tearDown(self):
        for path in FIXTURES.glob("*"):
            path.unlink()
        FIXTURES.rmdir()

    def _haystack(self, positions, shape=(300, 220)):
        haystack = np.zeros((*shape, 3), dtype=np.uint8)
        haystack[:] = (30, 30, 30)
        for x, y in positions:
            haystack[y : y + 12, x : x + 12] = self.icon
        return haystack

    def test_templates_are_prepared_once(self):
        vision = Vision([str(self.icon_path), str(self.icon_alpha_path)])
        for needle in vision.needle_imgs:
            self.assertEqual(needle.ndim, 3)
            self.assertEqual(needle.shape[2], 3)
            self.assertEqual(needle.dtype, np.uint8)
            self.assertTrue(needle.flags["C_CONTIGUOUS"])

    def test_unreadable_template_is_skipped(self):
        broken = FIXTURES / "broken.png"
        broken.write_bytes(b"not an image")
        vision = Vision([str(broken), str(self.icon_path)])
        self.assertEqual(len(vision.needle_imgs), 1)
        self.assertTrue(vision.has_templates)

    def test_no_templates(self):
        vision = Vision([])
        self.assertFalse(vision.has_templates)
        points, _ = vision.detect(self._haystack([]), 90)
        self.assertEqual(points, [])

    def test_each_icon_is_found_once(self):
        vision = Vision([str(self.icon_path)])
        positions = [(20, 30), (20, 80), (100, 200)]
        points, _ = vision.detect(self._haystack(positions), 90)
        expected = sorted(((x + 6, y + 6) for x, y in positions), key=lambda p: (p[1], p[0]))
        self.assertEqual(points, expected)

    def test_variants_of_same_icon_count_once(self):
        # Two templates matching the same spot must give one detection
        vision = Vision([str(self.icon_path), str(self.icon_alpha_path)])
        points, _ = vision.detect(self._haystack([(40, 40)]), 90)
        self.assertEqual(points, [(46, 46)])

    def test_empty_region_has_no_detection(self):
        vision = Vision([str(self.icon_path)])
        points, _ = vision.detect(self._haystack([]), 90)
        self.assertEqual(points, [])

    def test_non_contiguous_input(self):
        # mss gives BGRA; slicing off alpha creates a non-contiguous view
        vision = Vision([str(self.icon_path)])
        bgra = cv.cvtColor(self._haystack([(50, 60)]), cv.COLOR_BGR2BGRA)
        points, _ = vision.detect(bgra[:, :, :3], 90)
        self.assertEqual(points, [(56, 66)])

    def test_annotate_does_not_modify_input(self):
        vision = Vision([str(self.icon_path)])
        haystack = self._haystack([(50, 60)])
        original = haystack.copy()
        points, annotated = vision.detect(haystack, 90, annotate=True)
        self.assertEqual(len(points), 1)
        np.testing.assert_array_equal(haystack, original)
        self.assertFalse(np.array_equal(annotated, original))

    def test_region_too_small_raises(self):
        vision = Vision([str(self.icon_path)])
        with self.assertRaises(RegionSizeError):
            vision.detect(np.zeros((5, 5, 3), dtype=np.uint8), 90)

    def test_missing_image_raises(self):
        vision = Vision([str(self.icon_path)])
        with self.assertRaises(ScreenshotError):
            vision.detect(None, 90)

    def test_find_returns_empty_list_on_error(self):
        vision = Vision([str(self.icon_path)])
        with patch("cv2.destroyWindow"):
            self.assertEqual(vision.find(np.zeros((5, 5, 3), dtype=np.uint8)), [])

    def test_low_threshold_stays_fast(self):
        # A threshold of 0 matches nearly every position. Grouping must stay
        # fast instead of comparing every candidate with every other one.
        vision = Vision([str(self.icon_path)])
        rng = np.random.default_rng(1)
        haystack = rng.integers(0, 256, (600, 400, 3), dtype=np.uint8)
        start = time.perf_counter()
        points, _ = vision.detect(haystack, 0)
        elapsed = time.perf_counter() - start
        self.assertLessEqual(len(points), DETECTION_MAX_CANDIDATES)
        self.assertLess(elapsed, 2.0)

    def test_debug_window_is_closed_after_disable(self):
        vision = Vision([str(self.icon_path)])
        haystack = self._haystack([(50, 60)])
        vision.debug_mode = True
        with patch("cv2.imshow") as imshow, patch("cv2.waitKey"), patch(
            "cv2.destroyWindow"
        ) as destroy:
            vision.find(haystack, 90)
            imshow.assert_called_once()
            self.assertEqual(imshow.call_args[0][0], "Enemy Vision")

            vision.debug_mode = False
            vision.find(haystack, 90)
            destroy.assert_called_once_with("Enemy Vision")

            # Closing again does nothing
            vision.find(haystack, 90)
            destroy.assert_called_once()

    def test_window_errors_do_not_raise(self):
        vision = Vision([str(self.icon_path)])
        with patch("cv2.destroyWindow", side_effect=cv.error("no gui")):
            vision.destroy_vision("Enemy")
        with patch("cv2.destroyAllWindows", side_effect=cv.error("no gui")):
            vision.clean_up()


class NonMaxSuppressionTests(unittest.TestCase):
    """Grouping of overlapping matches."""

    def test_overlapping_boxes_are_merged(self):
        boxes = np.array([[10, 10, 12, 12], [11, 10, 12, 12], [10, 11, 12, 12]])
        scores = np.array([0.9, 0.95, 0.8])
        kept = _non_max_suppression(boxes, scores, 0.3)
        self.assertEqual(len(kept), 1)
        np.testing.assert_array_equal(kept[0], [11, 10, 12, 12])

    def test_separate_boxes_are_kept(self):
        boxes = np.array([[10, 10, 12, 12], [10, 40, 12, 12]])
        scores = np.array([0.9, 0.95])
        self.assertEqual(len(_non_max_suppression(boxes, scores, 0.3)), 2)

    def test_empty(self):
        self.assertEqual(_non_max_suppression(np.empty((0, 4)), np.empty(0), 0.3), [])


class WindowCaptureTests(unittest.TestCase):
    """Screen capture with a reused mss instance."""

    def test_invalid_region_returns_none(self):
        capture = WindowCapture(MagicMock())
        with patch("evealert.tools.windowscapture.mss.mss") as mss_factory:
            self.assertEqual(capture.get_screenshot_value(10, 10, 5, 20), (None, None))
            mss_factory.assert_not_called()

    def test_instance_is_reused_and_output_is_contiguous_bgr(self):
        capture = WindowCapture(MagicMock())
        frame = np.zeros((20, 30, 4), dtype=np.uint8)
        frame[:, :, 0] = 1  # B
        frame[:, :, 3] = 255  # A
        sct = MagicMock()
        sct.grab.return_value = frame
        with patch("evealert.tools.windowscapture.mss.mss", return_value=sct) as factory:
            img, _ = capture.get_screenshot_value(0, 0, 30, 20)
            capture.get_screenshot_value(0, 0, 30, 20)
        factory.assert_called_once()
        self.assertEqual(img.shape, (20, 30, 3))
        self.assertTrue(img.flags["C_CONTIGUOUS"])
        self.assertTrue((img[:, :, 0] == 1).all())

    def test_failed_grab_recreates_instance(self):
        capture = WindowCapture(MagicMock())
        sct = MagicMock()
        sct.grab.side_effect = RuntimeError("display changed")
        with patch("evealert.tools.windowscapture.mss.mss", return_value=sct) as factory:
            self.assertEqual(capture.get_screenshot_value(0, 0, 30, 20), (None, None))
            capture.get_screenshot_value(0, 0, 30, 20)
        self.assertEqual(factory.call_count, 2)
        sct.close.assert_called()


if __name__ == "__main__":
    unittest.main()
