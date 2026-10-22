"""Enemy alarms are skipped in the systems from the settings (F3 region)."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np

from evealert.manager.alertmanager import AlertAgent


def make_settings(system="Jita", region=True):
    settings = {
        "alert_region_1": {"x": 100, "y": 100},
        "alert_region_2": {"x": 300, "y": 300},
        "faction_region_1": {"x": 400, "y": 100},
        "faction_region_2": {"x": 600, "y": 300},
        "detectionscale": {"value": 90},
        "faction_scale": {"value": 85},
        "cooldown_timer": {"value": 30},
        "volume": {"value": 100},
        "server": {"name": "", "system": system, "mute": False},
    }
    if region:
        settings["system_region_1"] = {"x": 10, "y": 10}
        settings["system_region_2"] = {"x": 200, "y": 30}
    return settings


class LocationTests(unittest.TestCase):
    def make_agent(self, settings):
        main = MagicMock()
        main.menu.setting.read_settings.return_value = settings
        main.menu.setting.is_changed = False
        with patch("evealert.manager.alertmanager.AlertAgent._validate_audio_files"):
            agent = AlertAgent(main)
        agent.wincap = MagicMock()
        agent.wincap.get_screenshot_value.return_value = (
            np.zeros((20, 190, 3), dtype=np.uint8),
            None,
        )
        agent.system_reader = MagicMock()
        return agent, main

    def messages(self, main):
        return [call.args[0] for call in main.write_message.call_args_list]

    def test_region_from_settings(self):
        agent, _ = self.make_agent(make_settings())
        self.assertTrue(agent.has_system_region)
        self.assertTrue(agent.system_check_enabled)
        self.assertEqual(
            (agent.x1_system, agent.y1_system, agent.x2_system, agent.y2_system),
            (10, 10, 200, 30),
        )

    def test_no_region_means_no_check(self):
        agent, _ = self.make_agent(make_settings(region=False))
        self.assertFalse(agent.has_system_region)
        agent.update_location()
        self.assertIsNone(agent.in_ignored_system)
        agent.system_reader.read.assert_not_called()

    def test_in_ignored_system(self):
        agent, main = self.make_agent(make_settings("Jita, Perimeter"))
        agent.system_reader.read.return_value = "Jita 1.0 < Kimotoro < The Forge"
        agent.update_location()
        self.assertEqual(agent.current_system, "Jita")
        self.assertEqual(agent.in_ignored_system, "Jita")
        self.assertEqual(agent.alert_system_name, "Jita")
        self.assertTrue(any("pomijane" in m for m in self.messages(main)))

        # Jumping to another system turns the alarms back on
        agent.system_reader.read.return_value = "Niyabainen 1.0 < Kimotoro"
        agent.update_location()
        self.assertIsNone(agent.in_ignored_system)
        self.assertEqual(agent.alert_system_name, "Niyabainen")
        self.assertTrue(any("Opuściłeś Jita" in m for m in self.messages(main)))

    def test_unreadable_text_keeps_alarms_on(self):
        agent, _ = self.make_agent(make_settings())
        agent.system_reader.read.return_value = ""
        agent.update_location()
        self.assertIsNone(agent.in_ignored_system)
        self.assertTrue(agent.system_check_enabled)
        # Messages fall back to the name from the settings
        self.assertEqual(agent.alert_system_name, "Jita")

    def test_ocr_failure_disables_check(self):
        agent, main = self.make_agent(make_settings())
        agent.system_reader.read.return_value = None
        agent.system_reader.error = "no module"
        agent.update_location()
        self.assertFalse(agent.system_check_enabled)
        self.assertIsNone(agent.in_ignored_system)
        self.assertTrue(any("odczyt wyłączony" in m for m in self.messages(main)))

    def test_capture_failure_disables_check(self):
        agent, _ = self.make_agent(make_settings())
        agent.wincap.get_screenshot_value.return_value = (None, None)
        agent.update_location()
        self.assertFalse(agent.system_check_enabled)

    def run_one_check(self, agent, enemy=True):
        """Run one iteration of the alarm loop."""
        agent.update_detection = MagicMock(return_value=True)
        agent.enemy = enemy
        agent.faction = False
        agent.alarm_detection = AsyncMock()
        agent.reset_alarm = AsyncMock()

        def detection():
            agent.enemy = enemy
            return True

        agent.update_detection.side_effect = detection

        async def run():
            with patch(
                "evealert.manager.alertmanager.asyncio.sleep",
                AsyncMock(side_effect=asyncio.CancelledError),
            ):
                try:
                    await agent.run()
                except asyncio.CancelledError:
                    pass

        asyncio.run(run())

    def test_enemy_alarm_skipped_in_ignored_system(self):
        agent, main = self.make_agent(make_settings())
        agent.system_reader.read.return_value = "Jita 1.0 < Kimotoro"
        self.run_one_check(agent)
        agent.alarm_detection.assert_not_called()
        agent.reset_alarm.assert_any_call("Enemy")
        self.assertTrue(any("pominięty" in m for m in self.messages(main)))

    def test_enemy_alarm_elsewhere(self):
        agent, _ = self.make_agent(make_settings())
        agent.system_reader.read.return_value = "Perimeter 1.0 < Kimotoro"
        self.run_one_check(agent)
        agent.alarm_detection.assert_called_once()
        self.assertEqual(agent.alarm_detection.call_args.args[0], "Wróg w Local!")

    def test_webhook_uses_read_system_name(self):
        agent, main = self.make_agent(make_settings())
        main.webhook = MagicMock()
        agent.current_system = "Perimeter"
        agent._execute_webhook = AsyncMock(return_value=True)
        asyncio.run(agent.send_webhook_message("Enemy"))
        agent._execute_webhook.assert_called_once_with("Wróg w Perimeter!")


if __name__ == "__main__":
    unittest.main()
