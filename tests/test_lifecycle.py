"""Tests for starting and stopping the alert worker thread."""

import copy
import threading
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import cv2 as cv
import numpy as np

from evealert.manager import alertmanager
from evealert.manager.alertmanager import ALERT_FILES, AlertAgent

SETTINGS = {
    "alert_region_1": {"x": 0, "y": 0},
    "alert_region_2": {"x": 200, "y": 200},
    "faction_region_1": {"x": 0, "y": 0},
    "faction_region_2": {"x": 200, "y": 200},
    "detectionscale": {"value": 90},
    "faction_scale": {"value": 90},
    "cooldown_timer": {"value": 30},
    "volume": {"value": 100},
    "server": {"name": "", "system": "Jita", "mute": False},
}


def _wait_for(condition, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.01)
    return False


def _haystack(with_enemy: bool) -> np.ndarray:
    haystack = np.full((200, 200, 3), 20, dtype=np.uint8)
    if with_enemy:
        icon = cv.imread(ALERT_FILES[0], cv.IMREAD_COLOR)
        haystack[50 : 50 + icon.shape[0], 60 : 60 + icon.shape[1]] = icon
    return haystack


class LifecycleTests(unittest.TestCase):
    """Worker thread start/stop behaviour."""

    def setUp(self):
        self.main = MagicMock()
        self.main.webhook = None
        self.messages = []
        self.main.write_message.side_effect = lambda text, color="normal": self.messages.append(
            (text, color)
        )
        # Run GUI calls directly in tests
        self.main.run_in_ui.side_effect = lambda func, *a, **kw: func(*a, **kw)
        self.main.menu.setting.read_settings.side_effect = lambda: copy.deepcopy(SETTINGS)
        self.main.menu.setting.is_changed = False

        patches = [
            patch.object(alertmanager, "MAIN_CHECK_SLEEP_MIN", 0.01),
            patch.object(alertmanager, "MAIN_CHECK_SLEEP_MAX", 0.02),
            patch("evealert.manager.alertmanager.AlertAgent._validate_audio_files"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        self.agent = AlertAgent(self.main)
        self.agent.play_sound = AsyncMock()
        self.frame = _haystack(with_enemy=True)
        self.agent.wincap.get_screenshot_value = MagicMock(
            side_effect=lambda *a: (self.frame, None)
        )
        self.addCleanup(self.agent.clean_up)

    def _texts(self):
        return [text for text, _ in self.messages]

    def test_start_detect_stop_and_restart(self):
        self.assertTrue(self.agent.start())
        self.assertTrue(self.agent.is_running)
        self.assertTrue(_wait_for(lambda: self.agent.play_sound.await_count > 0))
        self.assertTrue(self.agent.is_enemy)
        self.assertIn("Enemy Appears!", self._texts())
        self.assertIsNot(threading.current_thread(), self.agent._thread)

        self.agent.stop()
        self.assertTrue(_wait_for(lambda: not self.agent.is_alive))
        self.assertFalse(self.agent.is_running)
        self.assertFalse(self.agent.is_enemy)
        self.assertIn("System: EVE Alert stopped.", self._texts())
        self.main.update_alert_button.assert_called()

        # A second start uses a new event loop and lock
        self.assertTrue(self.agent.start())
        self.assertTrue(_wait_for(lambda: self.agent.play_sound.await_count > 1))
        self.agent.stop()
        self.assertTrue(_wait_for(lambda: not self.agent.is_alive))

    def test_double_start_is_rejected(self):
        self.assertTrue(self.agent.start())
        self.assertFalse(self.agent.start())
        self.assertIn("System: EVE Alert is already running.", self._texts())

    def test_no_enemy_no_alarm(self):
        self.frame = _haystack(with_enemy=False)
        self.agent.start()
        self.assertTrue(_wait_for(lambda: any("Next check" in t for t in self._texts())))
        self.assertFalse(self.agent.is_enemy)
        self.agent.play_sound.assert_not_awaited()

    def test_capture_failure_stops_with_message(self):
        self.agent.wincap.get_screenshot_value = MagicMock(return_value=(None, None))
        self.agent.start()
        self.assertTrue(_wait_for(lambda: not self.agent.is_alive))
        self.assertFalse(self.agent.is_running)
        self.assertTrue(any("could not be captured" in t for t in self._texts()))
        self.assertIn("System: EVE Alert stopped.", self._texts())

    def test_unexpected_error_stops_with_message(self):
        self.agent.update_detection = MagicMock(side_effect=RuntimeError("boom"))
        self.agent.start()
        self.assertTrue(_wait_for(lambda: not self.agent.is_alive))
        self.assertFalse(self.agent.is_running)
        self.assertTrue(any("because of an error" in t for t in self._texts()))

    def test_faction_failure_disables_only_faction(self):
        def capture(y1, x1, x2, y2):
            # Faction region has a different size in this test
            if (x2, y2) == (150, 150):
                return None, None
            return self.frame, None

        settings = copy.deepcopy(SETTINGS)
        settings["faction_region_2"] = {"x": 150, "y": 150}
        self.main.menu.setting.read_settings.side_effect = lambda: copy.deepcopy(settings)
        self.agent.wincap.get_screenshot_value = MagicMock(side_effect=capture)

        self.agent.start()
        self.assertTrue(_wait_for(lambda: self.agent.play_sound.await_count > 1))
        self.assertTrue(self.agent.is_alive)
        self.assertFalse(self.agent.faction_enabled)
        disabled = [t for t in self._texts() if t.startswith("Faction detection disabled")]
        self.assertEqual(len(disabled), 1)

    def test_invalid_settings_do_not_start(self):
        settings = copy.deepcopy(SETTINGS)
        settings["alert_region_2"] = {"x": 0, "y": 0}
        self.main.menu.setting.read_settings.side_effect = lambda: copy.deepcopy(settings)
        self.assertFalse(self.agent.start())
        self.assertIsNone(self.agent._thread)
        self.assertFalse(self.agent.is_running)

    def test_settings_reload_in_worker(self):
        self.agent.start()
        self.assertTrue(_wait_for(lambda: self.agent.play_sound.await_count > 0))

        settings = copy.deepcopy(SETTINGS)
        settings["detectionscale"]["value"] = 55
        settings["server"]["system"] = "Amarr"
        self.main.menu.setting.read_settings.side_effect = lambda: copy.deepcopy(settings)
        self.main.menu.setting.is_changed = True

        self.assertTrue(_wait_for(lambda: self.agent.detection == 55))
        self.assertEqual(self.agent.system_name, "Amarr")
        self.assertFalse(self.main.menu.setting.changed)

    def test_clean_up_joins_thread(self):
        self.agent.start()
        self.assertTrue(_wait_for(lambda: self.agent.play_sound.await_count > 0))
        self.agent.clean_up()
        self.assertFalse(self.agent.is_alive)

    def test_stop_when_not_running_is_safe(self):
        self.agent.stop()
        self.agent.clean_up()
        self.assertFalse(self.agent.is_running)


class WebhookTests(unittest.IsolatedAsyncioTestCase):
    """Webhook calls must not block or break the alarm loop."""

    async def asyncSetUp(self):
        self.main = MagicMock()
        self.main.menu.setting.read_settings.return_value = copy.deepcopy(SETTINGS)
        with patch("evealert.manager.alertmanager.AlertAgent._validate_audio_files"):
            self.agent = AlertAgent(self.main)

    async def test_webhook_uses_system_name_from_settings(self):
        await self.agent.send_webhook_message("Enemy")
        self.main.webhook.execute.assert_called_once_with("Enemy Appears in Jita!")
        self.assertTrue(self.agent.webhook_sent)

    async def test_webhook_without_system_name(self):
        self.agent.system_name = ""
        await self.agent.send_webhook_message("Enemy")
        self.main.webhook.execute.assert_called_once_with("Enemy Appears!")

    async def test_webhook_error_is_handled(self):
        self.main.webhook.execute.side_effect = RuntimeError("discord down")
        await self.agent.send_webhook_message("Enemy")
        self.assertFalse(self.agent.webhook_sent)

    async def test_reset_error_is_handled(self):
        self.agent.webhook_sent = True
        self.main.webhook.execute.side_effect = RuntimeError("discord down")
        await self.agent.reset_alarm("Enemy")
        self.assertFalse(self.agent.webhook_sent)


if __name__ == "__main__":
    unittest.main()
