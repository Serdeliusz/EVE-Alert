import threading
from typing import TYPE_CHECKING, Optional, Tuple

import mss
import numpy as np

from evealert.settings.logger import logging

if TYPE_CHECKING:
    from evealert.menu.main import MainMenu

logger = logging.getLogger("tools")


class WindowCapture:
    """Handles screen capture for specified regions.

    One ``mss`` instance is kept per thread and reused for every capture.
    Creating a new instance for each screenshot is slow, and on Windows an
    ``mss`` instance must not be shared between threads.
    """

    def __init__(self, mainmenu: "MainMenu"):
        self.main = mainmenu
        self._local = threading.local()

    def _get_sct(self) -> "mss.base.MSSBase":
        """Return the ``mss`` instance of the calling thread."""
        sct = getattr(self._local, "sct", None)
        if sct is None:
            sct = mss.mss()
            self._local.sct = sct
        return sct

    def close(self) -> None:
        """Release the ``mss`` instance of the calling thread."""
        sct = getattr(self._local, "sct", None)
        if sct is not None:
            try:
                sct.close()
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.debug("Closing screen capture failed: %s", e)
            self._local.sct = None

    def get_screenshot_value(
        self, y1: int, x1: int, x2: int, y2: int
    ) -> Tuple[Optional[np.ndarray], Optional["mss.screenshot.ScreenShot"]]:
        """
        Capture a screenshot of the specified region.

        Args:
            y1: Top coordinate
            x1: Left coordinate
            x2: Right coordinate (exclusive)
            y2: Bottom coordinate (exclusive)

        Returns:
            Tuple of (numpy_array, raw_screenshot) or (None, None) on error.
            The array is a contiguous BGR image.
        """
        width = x2 - x1
        height = y2 - y1
        if width <= 0 or height <= 0:
            logger.error(
                "Screenshot capture failed: invalid region (%s, %s) to (%s, %s)",
                x1,
                y1,
                x2,
                y2,
            )
            return None, None

        monitor = {"top": y1, "left": x1, "width": width, "height": height}
        try:
            screenshot = self._get_sct().grab(monitor)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Screenshot capture failed: %s", e)
            # The instance may be broken (e.g. after a display change);
            # a new one is created on the next capture.
            self.close()
            return None, None

        # mss returns BGRA. Drop alpha and make the array contiguous so
        # OpenCV can use it without another copy.
        img_array = np.ascontiguousarray(np.asarray(screenshot)[:, :, :3])

        return img_array, screenshot
