"""Hint texts in the settings window must never be used as values."""

import unittest

from evealert.menu.setting import (
    IGNORED_SYSTEMS_PLACEHOLDER,
    SYSTEM_NAME_PLACEHOLDER,
    WEBHOOK_PLACEHOLDER,
    SettingMenu,
)


class PlaceholderTests(unittest.TestCase):
    """Settings written by older versions contain the hint texts."""

    def test_old_hint_texts_are_removed(self):
        settings = {
            "server": {
                "name": WEBHOOK_PLACEHOLDER,
                "system": SYSTEM_NAME_PLACEHOLDER,
                "ignored_systems": IGNORED_SYSTEMS_PLACEHOLDER,
                "mute": False,
            }
        }
        cleaned = SettingMenu._strip_placeholders(settings)
        self.assertEqual(cleaned["server"]["name"], "")
        self.assertEqual(cleaned["server"]["system"], "")
        self.assertEqual(cleaned["server"]["ignored_systems"], "")
        self.assertFalse(cleaned["server"]["mute"])

    def test_real_values_are_kept(self):
        settings = {
            "server": {
                "name": " https://discord.com/api/webhooks/1/x ",
                "system": "Jita",
            }
        }
        cleaned = SettingMenu._strip_placeholders(settings)
        self.assertEqual(
            cleaned["server"]["name"], "https://discord.com/api/webhooks/1/x"
        )
        self.assertEqual(cleaned["server"]["system"], "Jita")

    def test_invalid_types_become_empty(self):
        cleaned = SettingMenu._strip_placeholders(
            {"server": {"name": None, "system": 5}}
        )
        self.assertEqual(
            cleaned["server"], {"name": "", "system": "", "ignored_systems": ""}
        )


if __name__ == "__main__":
    unittest.main()
