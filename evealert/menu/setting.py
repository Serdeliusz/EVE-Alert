import copy
import json
from typing import TYPE_CHECKING

import customtkinter
from dhooks_lite import Webhook

from evealert.settings.helper import get_resource_path
from evealert.settings.logger import logging

if TYPE_CHECKING:
    from evealert.menu.main import MainMenu

logger = logging.getLogger("menu")

# Hint texts shown in empty entry fields. They disappear when the field is
# clicked and are never saved as values.
WEBHOOK_PLACEHOLDER = "Wklej link webhooka"
SYSTEM_NAME_PLACEHOLDER = "np. Jita (kilka: Jita, Perimeter)"
# Older versions saved the English hint texts as values
PLACEHOLDER_VALUES = {
    WEBHOOK_PLACEHOLDER,
    SYSTEM_NAME_PLACEHOLDER,
    "Enter a Webhook URL",
    "Enter a System Name",
    "np. Jita",
}

DEFAULT_SETTINGS = {
    "logging": "INFO",
    "alert_region_1": {"x": 0, "y": 0},
    "alert_region_2": {"x": 0, "y": 0},
    "faction_region_1": {"x": 0, "y": 0},
    "faction_region_2": {"x": 0, "y": 0},
    # Region with the name of the current solar system (F3). All zeros means
    # "not set": enemy alarms are then never skipped.
    "system_region_1": {"x": 0, "y": 0},
    "system_region_2": {"x": 0, "y": 0},
    "detectionscale": {"value": 90},
    "faction_scale": {"value": 90},
    "cooldown_timer": {"value": 30},
    "volume": {"value": 100},
    "server": {
        "name": "",
        "system": "",
        "mute": False,
    },
}


class SettingMenu:
    """Setting menu for the Alert System."""

    def __init__(self, main: "MainMenu"):
        self.main = main
        self.open = False
        self.default = DEFAULT_SETTINGS
        self.changed = False

        self.setting_window = customtkinter.CTkToplevel(self.main)
        self.setting_window.title("Ustawienia")
        self.setting_window.withdraw()

        self.play_alarm = customtkinter.BooleanVar()

        self.create_menu()

    @property
    def is_changed(self):
        """Returns True if the settings have been changed."""
        return self.changed

    @property
    def is_open(self):
        """Returns True if the settings window is open."""
        return self.open

    def read_settings(self):
        """Read the settings file merged with the defaults.

        Has no side effects: it does not write the file and does not touch
        any widget, so it is safe to call from the alert worker thread.

        Returns:
            A new settings dictionary
        """
        config_path = get_resource_path("settings.json")
        try:
            with open(config_path, encoding="utf-8") as config_file:
                settings = json.load(config_file)
            if not isinstance(settings, dict):
                raise ValueError("settings.json must contain an object")
            return self._strip_placeholders(self.merge_settings_with_defaults(settings))
        except (OSError, ValueError) as e:
            # json.JSONDecodeError is a ValueError
            logger.debug(
                "Setting Menu: Error reading settings file (%s). Using default settings.",
                e,
            )
            return copy.deepcopy(self.default)

    @staticmethod
    def _strip_placeholders(settings):
        """Replace hint texts saved by older versions with empty values."""
        server = settings.get("server")
        if isinstance(server, dict):
            for key in ("name", "system"):
                value = server.get(key)
                if not isinstance(value, str) or value.strip() in PLACEHOLDER_VALUES:
                    server[key] = ""
                else:
                    server[key] = value.strip()
        return settings

    @staticmethod
    def _set_entry_text(entry, value) -> None:
        """Replace the text of an entry; an empty value shows its hint text."""
        entry.delete(0, customtkinter.END)
        if value not in (None, ""):
            entry.insert(0, value)
        elif hasattr(entry, "_activate_placeholder"):
            # A new CTkEntry counts as focused until it loses focus once, so
            # delete() alone does not bring the hint text back.
            entry._activate_placeholder()

    def load_settings(self):
        """Read the settings, write them back normalized and show them in the menu.

        Must be called from the GUI thread.
        """
        settings = self.read_settings()
        self.save_settings(settings)
        self.apply_settings(settings)
        return settings

    def merge_settings_with_defaults(self, settings, defaults=None):
        """Merge the loaded settings with the default settings recursively."""
        if defaults is None:
            defaults = self.default

        merged_settings = copy.deepcopy(defaults)
        for key, value in defaults.items():
            if key in settings:
                if isinstance(value, dict) and isinstance(settings[key], dict):
                    # Recursively merge nested dictionaries
                    merged_settings[key] = self.merge_settings_with_defaults(
                        settings[key], value
                    )
                else:
                    merged_settings[key] = settings[key]
            else:
                # Fill missing keys with default values
                merged_settings[key] = value

        return merged_settings

    def _activate_webhook(self, webhookurl):
        """Activate the webhook URL."""
        try:
            required_prefix = "https://discord.com/api/webhooks/"
            if not webhookurl.startswith(required_prefix):
                raise ValueError(f"Adres musi zaczynać się od '{required_prefix}'.")
            self.main.webhook = Webhook(
                webhookurl,
                username="Gneuten",
                avatar_url="https://cdn.discordapp.com/avatars/990582360103870495/410d536127874481b9771b9eb9aa8104.png",
            )
            return True
        except ValueError as e:
            logger.error("Invalid webhook URL: %s", e)
            self.main.webhook = None
            return False
        except Exception as e:
            logger.error("Error activating webhook: %s", e)
            self.main.webhook = None
            return False

    def apply_settings(self, settings):
        try:
            self.logging.delete(0, customtkinter.END)
            self.logging.insert(0, settings["logging"])

            self.alert_region_x_first.delete(0, customtkinter.END)
            self.alert_region_x_first.insert(0, settings["alert_region_1"]["x"])

            self.alert_region_y_first.delete(0, customtkinter.END)
            self.alert_region_y_first.insert(0, settings["alert_region_1"]["y"])

            self.alert_region_x_second.delete(0, customtkinter.END)
            self.alert_region_x_second.insert(0, settings["alert_region_2"]["x"])
            self.alert_region_y_second.delete(0, customtkinter.END)
            self.alert_region_y_second.insert(0, settings["alert_region_2"]["y"])

            self.faction_region_x_first.delete(0, customtkinter.END)
            self.faction_region_x_first.insert(0, settings["faction_region_1"]["x"])
            self.faction_region_y_first.delete(0, customtkinter.END)
            self.faction_region_y_first.insert(0, settings["faction_region_1"]["y"])

            self.faction_region_x_second.delete(0, customtkinter.END)
            self.faction_region_x_second.insert(0, settings["faction_region_2"]["x"])
            self.faction_region_y_second.delete(0, customtkinter.END)
            self.faction_region_y_second.insert(0, settings["faction_region_2"]["y"])

            self.detectionscale.set(settings["detectionscale"]["value"])
            self.slider_event(settings["detectionscale"]["value"])
            self.faction_scale.set(settings["faction_scale"]["value"])
            self.factionslider_event(settings["faction_scale"]["value"])

            self.system_region_x_first.delete(0, customtkinter.END)
            self.system_region_x_first.insert(0, settings["system_region_1"]["x"])
            self.system_region_y_first.delete(0, customtkinter.END)
            self.system_region_y_first.insert(0, settings["system_region_1"]["y"])

            self.system_region_x_second.delete(0, customtkinter.END)
            self.system_region_x_second.insert(0, settings["system_region_2"]["x"])
            self.system_region_y_second.delete(0, customtkinter.END)
            self.system_region_y_second.insert(0, settings["system_region_2"]["y"])

            self.cooldown_timer.delete(0, customtkinter.END)
            self.cooldown_timer.insert(0, settings["cooldown_timer"]["value"])

            self.volume_scale.set(settings["volume"]["value"])
            self.volumeslider_event(settings["volume"]["value"])

            self._set_entry_text(self.system_name, settings["server"]["system"])

            webhook_url = settings["server"]["name"]
            self._set_entry_text(self.webhook, webhook_url)
            if webhook_url:
                self._activate_webhook(webhook_url)
            else:
                self.main.webhook = None

            self.play_alarm.set(settings["server"]["mute"])

        except KeyError as e:
            logger.exception(e)
            self.main.write_message(
                "Ustawienia: błąd odczytu pliku ustawień, szczegóły w logach.",
                "red",
            )

    def save_settings(self, settings=None):
        if settings is None:
            settings = copy.deepcopy(self.default)

        config_path = get_resource_path("settings.json")
        with open(config_path, encoding="utf-8", mode="w") as config_file:
            json.dump(settings, config_file, indent=4)

        self.apply_settings(settings)
        # Set the changed flag to True
        self.changed = True

    def save(self):
        """Save settings to disk only (does not apply to running system)."""
        try:
            settings = copy.deepcopy(DEFAULT_SETTINGS)
            settings.update(
                {
                    "logging": self.logging.get(),
                    "alert_region_1": {
                        "x": int(self.alert_region_x_first.get()),
                        "y": int(self.alert_region_y_first.get()),
                    },
                    "alert_region_2": {
                        "x": int(self.alert_region_x_second.get()),
                        "y": int(self.alert_region_y_second.get()),
                    },
                    "faction_region_1": {
                        "x": int(self.faction_region_x_first.get()),
                        "y": int(self.faction_region_y_first.get()),
                    },
                    "faction_region_2": {
                        "x": int(self.faction_region_x_second.get()),
                        "y": int(self.faction_region_y_second.get()),
                    },
                    "system_region_1": {
                        "x": int(self.system_region_x_first.get()),
                        "y": int(self.system_region_y_first.get()),
                    },
                    "system_region_2": {
                        "x": int(self.system_region_x_second.get()),
                        "y": int(self.system_region_y_second.get()),
                    },
                    "detectionscale": {"value": int(self.detectionscale.get())},
                    "faction_scale": {"value": int(self.faction_scale.get())},
                    "cooldown_timer": {"value": int(self.cooldown_timer.get())},
                    "volume": {"value": int(self.volume_scale.get())},
                    "server": {
                        "name": self.webhook.get().strip(),
                        "system": self.system_name.get().strip(),
                        "mute": self.play_alarm.get(),
                    },
                }
            )
            self.save_settings(settings)
            self.main.write_message("Ustawienia: zapisano na dysku.", "green")
        except ValueError as e:
            self.main.write_message(
                "Ustawienia: błąd zapisu. Sprawdź wpisane wartości.", "red"
            )
            logger.error(e)

    def apply_settings_runtime(self):
        """Apply settings to the running system without restart."""
        try:
            # Validate settings first
            # pylint: disable=import-outside-toplevel
            from evealert.settings.validator import ConfigValidator

            detection_scale = int(self.detectionscale.get())
            faction_scale = int(self.faction_scale.get())
            cooldown = int(self.cooldown_timer.get())
            volume = int(self.volume_scale.get())
            mute = self.play_alarm.get()

            # Validate detection scales
            is_valid, error = ConfigValidator.validate_detection_scale(detection_scale)
            if not is_valid:
                self.main.write_message(f"Błąd walidacji: {error}", "red")
                return

            is_valid, error = ConfigValidator.validate_detection_scale(faction_scale)
            if not is_valid:
                self.main.write_message(f"Błąd walidacji: {error}", "red")
                return

            # Validate cooldown
            is_valid, error = ConfigValidator.validate_cooldown_timer(cooldown)
            if not is_valid:
                self.main.write_message(f"Błąd walidacji: {error}", "red")
                return

            # Apply to AlertAgent if running
            if self.main.alert:
                self.main.alert.detection = detection_scale
                self.main.alert.detection_faction = faction_scale
                self.main.alert.cooldowntimer = cooldown
                self.main.alert.volume = volume / 100.0  # Convert to 0.0-1.0
                self.main.alert.mute = mute
                self.main.alert.system_name = self.system_name.get().strip()

                # Update webhook if changed
                webhook_url = self.webhook.get().strip()
                if webhook_url:
                    self._activate_webhook(webhook_url)
                else:
                    self.main.webhook = None

                self.main.write_message(
                    "Ustawienia: zastosowano w działającym systemie.", "green"
                )
                logger.info(
                    "Runtime settings applied: detection=%d, faction_scale=%d, cooldown=%d, mute=%s",
                    detection_scale,
                    faction_scale,
                    cooldown,
                    mute,
                )
            else:
                self.main.write_message(
                    "Ustawienia: system nie jest uruchomiony.", "yellow"
                )

        except ValueError as e:
            self.main.write_message(
                "Ustawienia: nieprawidłowe wartości. Sprawdź wpisane dane.", "red"
            )
            logger.error("Runtime settings apply error: %s", e)

    def clean_up(self):
        """Cleans up the settings window."""
        if self.is_open:
            self.open = False
            self.main.mainmenu_buttons.setting_menu.configure(
                fg_color="#1f538d", hover_color="#14375e"
            )
            # hide the settings window
            self.setting_window.withdraw()
            # self.save_settings()  # Save settings when closing

    def create_menu(self):
        """Load the settings from the settings file."""

        # Use a separate frame for the menu
        self.menu_frame = customtkinter.CTkFrame(self.setting_window)
        self.menu_frame.pack(side="left", padx=20, pady=20)

        self.logging = customtkinter.CTkEntry(self.menu_frame)

        # 1 Row - Init
        self.label_x_axis = customtkinter.CTkLabel(self.menu_frame, text="Oś X")
        self.label_y_axis = customtkinter.CTkLabel(self.menu_frame, text="Oś Y")

        # 2 Row - Init
        # Alert Region Position 1
        self.alert_region_label_1 = customtkinter.CTkLabel(
            self.menu_frame, text="Obszar alarmu – lewy górny róg:", justify="left"
        )
        self.alert_region_x_first = customtkinter.CTkEntry(self.menu_frame)
        self.alert_region_y_first = customtkinter.CTkEntry(self.menu_frame)

        # 3 Row - Init
        # Alert Region Position 2
        self.alert_region_label_2 = customtkinter.CTkLabel(
            self.menu_frame, text="Obszar alarmu – prawy dolny róg:", justify="left"
        )
        self.alert_region_x_second = customtkinter.CTkEntry(self.menu_frame)
        self.alert_region_y_second = customtkinter.CTkEntry(self.menu_frame)

        # 4 Row - Init
        # Alert Region Position 1
        self.faction_region_label_1 = customtkinter.CTkLabel(
            self.menu_frame, text="Obszar frakcji – lewy górny róg:", justify="left"
        )
        self.faction_region_x_first = customtkinter.CTkEntry(self.menu_frame)
        self.faction_region_y_first = customtkinter.CTkEntry(self.menu_frame)

        # 5 Row - Init
        # Alert Region Position 2
        self.faction_region_label_2 = customtkinter.CTkLabel(
            self.menu_frame, text="Obszar frakcji – prawy dolny róg:", justify="left"
        )
        self.faction_region_x_second = customtkinter.CTkEntry(self.menu_frame)
        self.faction_region_y_second = customtkinter.CTkEntry(self.menu_frame)

        # System name region (F3)
        self.system_region_label_1 = customtkinter.CTkLabel(
            self.menu_frame,
            text="Obszar nazwy systemu – lewy górny róg:",
            justify="left",
        )
        self.system_region_x_first = customtkinter.CTkEntry(self.menu_frame)
        self.system_region_y_first = customtkinter.CTkEntry(self.menu_frame)
        self.system_region_label_2 = customtkinter.CTkLabel(
            self.menu_frame,
            text="Obszar nazwy systemu – prawy dolny róg:",
            justify="left",
        )
        self.system_region_x_second = customtkinter.CTkEntry(self.menu_frame)
        self.system_region_y_second = customtkinter.CTkEntry(self.menu_frame)

        # Row 6 - Init
        # Slider
        self.slider_label = customtkinter.CTkLabel(
            self.menu_frame, text="Czułość wykrywania alarmu"
        )
        self.detectionscale = customtkinter.DoubleVar()
        self.slider = customtkinter.CTkSlider(
            self.menu_frame,
            from_=1,
            to=100,
            orientation="horizontal",
            number_of_steps=99,
            variable=self.detectionscale,
            command=self.slider_event,
        )

        # Row 7 - Init
        # Slider
        self.faction_slider_label = customtkinter.CTkLabel(
            self.menu_frame, text="Czułość wykrywania frakcji"
        )
        self.faction_scale = customtkinter.DoubleVar()
        self.slider2 = customtkinter.CTkSlider(
            self.menu_frame,
            from_=1,
            to=100,
            orientation="horizontal",
            number_of_steps=99,
            variable=self.faction_scale,
            command=self.factionslider_event,
        )

        # Row 8 - Init
        # Volume Slider
        self.volume_slider_label = customtkinter.CTkLabel(
            self.menu_frame, text="Głośność"
        )
        self.volume_scale = customtkinter.DoubleVar()
        self.volume_slider = customtkinter.CTkSlider(
            self.menu_frame,
            from_=0,
            to=100,
            orientation="horizontal",
            number_of_steps=100,
            variable=self.volume_scale,
            command=self.volumeslider_event,
        )

        self.cooldown_timer_label = customtkinter.CTkLabel(
            self.menu_frame, text="Przerwa między alarmami:", justify="left"
        )
        self.cooldown_timer = customtkinter.CTkEntry(self.menu_frame)
        self.cooldown_timer_text = customtkinter.CTkLabel(
            self.menu_frame, text="sekund", justify="left"
        )

        self.save_button = customtkinter.CTkButton(
            self.menu_frame, text="Zapisz", command=self.save
        )

        self.apply_button = customtkinter.CTkButton(
            self.menu_frame, text="Zastosuj", command=self.apply_settings_runtime
        )

        self.close_button = customtkinter.CTkButton(
            self.menu_frame, text="Zamknij", command=self.clean_up
        )

        self.empty_label_1 = customtkinter.CTkLabel(
            self.menu_frame, text=self.slider.get()
        )

        self.empty_label_2 = customtkinter.CTkLabel(
            self.menu_frame, text=self.slider2.get()
        )

        self.empty_label_3 = customtkinter.CTkLabel(
            self.menu_frame, text=f"{int(self.volume_slider.get())}%"
        )

        self.webhook_label = customtkinter.CTkLabel(
            self.menu_frame, text="Webhook Discord:", justify="left"
        )
        self.webhook = customtkinter.CTkEntry(
            self.menu_frame, placeholder_text=WEBHOOK_PLACEHOLDER
        )
        self.system_name_label = customtkinter.CTkLabel(
            self.menu_frame, text="Nazwa systemu:", justify="left"
        )
        self.system_name = customtkinter.CTkEntry(
            self.menu_frame, placeholder_text=SYSTEM_NAME_PLACEHOLDER
        )

        self.play_alarm_checkbox = customtkinter.CTkCheckBox(
            self.menu_frame, text="Wycisz alarm", variable=self.play_alarm
        )

        self.test_alarm_button = customtkinter.CTkButton(
            self.menu_frame, text="Testuj dźwięk alarmu", command=self.test_alarm_sound
        )

        self.test_faction_button = customtkinter.CTkButton(
            self.menu_frame,
            text="Testuj dźwięk frakcji",
            command=self.test_faction_sound,
        )

        # Init Visuals

        self.label_x_axis.grid(row=0, column=1)
        self.label_y_axis.grid(row=0, column=2)

        # Alert Region 1 Visual
        self.alert_region_label_1.grid(row=1, column=0, padx=20)
        self.alert_region_x_first.grid(row=1, column=1)
        self.alert_region_y_first.grid(row=1, column=2)

        # Alert Region 2 Visual
        self.alert_region_label_2.grid(row=2, column=0, padx=20)
        self.alert_region_x_second.grid(row=2, column=1, padx=20)
        self.alert_region_y_second.grid(row=2, column=2, padx=20)

        # Faction Region 1 Visual
        self.faction_region_label_1.grid(row=3, column=0, padx=20)
        self.faction_region_x_first.grid(row=3, column=1, padx=20)
        self.faction_region_y_first.grid(row=3, column=2, padx=20)

        # Faction Region 2 Visual
        self.faction_region_label_2.grid(row=4, column=0, padx=20)
        self.faction_region_x_second.grid(row=4, column=1, padx=20)
        self.faction_region_y_second.grid(row=4, column=2, padx=20)

        # System Name Region Visual
        self.system_region_label_1.grid(row=5, column=0, padx=20)
        self.system_region_x_first.grid(row=5, column=1, padx=20)
        self.system_region_y_first.grid(row=5, column=2, padx=20)
        self.system_region_label_2.grid(row=6, column=0, padx=20)
        self.system_region_x_second.grid(row=6, column=1, padx=20)
        self.system_region_y_second.grid(row=6, column=2, padx=20)

        # Cooldown Visual
        self.cooldown_timer_label.grid(row=7, column=0, padx=20)
        self.cooldown_timer.grid(row=7, column=1, padx=20)
        self.cooldown_timer_text.grid(row=7, column=2)

        # Slider Visual
        self.empty_label_1.grid(row=8, column=2)

        # Slider Visual
        self.slider_label.grid(row=8, column=0)
        self.slider.grid(row=8, column=1)

        # Slider Visual
        self.empty_label_2.grid(row=9, column=2)

        # Slider Visual
        self.faction_slider_label.grid(row=9, column=0)
        self.slider2.grid(row=9, column=1)

        # Volume Slider Visual
        self.empty_label_3.grid(row=10, column=2)
        self.volume_slider_label.grid(row=10, column=0)
        self.volume_slider.grid(row=10, column=1)

        # Webhook Visual
        self.webhook_label.grid(row=11, column=0)
        self.webhook.grid(row=11, column=1)

        # System Name Visual
        self.system_name_label.grid(row=12, column=0)
        self.system_name.grid(row=12, column=1)

        self.play_alarm_checkbox.grid(row=12, column=2)

        # Test Audio Buttons
        self.test_alarm_button.grid(row=13, column=0, pady=(10, 0))
        self.test_faction_button.grid(row=13, column=1, pady=(10, 0))

        # Save Button
        self.save_button.grid(row=14, column=0, pady=10)
        # Apply Button
        self.apply_button.grid(row=14, column=1, pady=10)
        # Close Button
        self.close_button.grid(row=14, column=2, pady=10)

        self.setting_window.protocol("WM_DELETE_WINDOW", self.clean_up)

    def open_menu(self):
        """Opens the settings window."""
        if not self.is_open:
            self.open = True
            self.main.mainmenu_buttons.setting_menu.configure(
                fg_color="#fa0202", hover_color="#bd291e"
            )

            # Position the description window to the right of the main menu
            config_menu_x, config_menu_y = (
                self.main.winfo_x(),
                self.main.winfo_y(),
            )
            config_menu_width, config_menu_height = (
                self.main.winfo_width(),
                self.main.winfo_height(),
            )

            # Size the window to its content
            self.setting_window.update_idletasks()
            config_window_width = max(650, self.setting_window.winfo_reqwidth())
            config_window_height = max(400, self.setting_window.winfo_reqheight())
            config_window_x = config_menu_x + config_menu_width + 10
            config_window_y = config_menu_y + config_menu_height + 40

            self.setting_window.geometry(
                f"{config_window_width}x{config_window_height}+{config_window_x}+{config_window_y}"
            )

            self.setting_window.deiconify()
        else:
            self.clean_up()

    def slider_event(self, slider_value):
        self.empty_label_1.configure(text=slider_value)

    def factionslider_event(self, slider_value):
        self.empty_label_2.configure(text=slider_value)

    def volumeslider_event(self, slider_value):
        self.empty_label_3.configure(text=f"{int(slider_value)}%")

    def _test_sound(self, sound_path: str, label: str) -> None:
        """Play a sound file once without blocking the GUI.

        Args:
            sound_path: Path to the WAV file
            label: Name used in the log messages (e.g. "Alarm")
        """
        # pylint: disable=import-outside-toplevel
        import numpy as np
        import sounddevice as sd
        import soundfile as sf

        from evealert.constants import AUDIO_CHANNELS

        if self.play_alarm.get():
            self.main.write_message(
                "Test dźwięku: dźwięk jest wyciszony. Odznacz 'Wycisz alarm', aby przetestować.",
                "yellow",
            )
            return

        try:
            data, samplerate = sf.read(sound_path, dtype="int16")
            if data.ndim == 1:
                # Convert Mono -> Stereo
                data = np.stack([data, data], axis=-1)
            elif data.ndim == 2 and data.shape[1] == 1:
                data = np.repeat(data, AUDIO_CHANNELS, axis=1)

            volume = int(self.volume_scale.get()) / 100.0
            data = (data * volume).astype("int16")

            # Non-blocking playback; report completion via the Tk event loop
            sd.play(data, samplerate)
            self.main.write_message(
                f"Test dźwięku: odtwarzam dźwięk {label}...", "green"
            )
            duration_ms = int(len(data) / samplerate * 1000)
            self.main.after(
                duration_ms,
                lambda: self.main.write_message(
                    f"Test dźwięku: dźwięk {label} zakończony.", "green"
                ),
            )
        except FileNotFoundError:
            self.main.write_message(
                f"Test dźwięku: nie znaleziono pliku: {sound_path}", "red"
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            self.main.write_message(f"Test dźwięku: błąd odtwarzania. {e}", "red")
            logger.exception("Error testing %s sound: %s", label, e)

    def test_alarm_sound(self):
        """Test alarm sound playback."""
        # pylint: disable=import-outside-toplevel
        from evealert.manager.alertmanager import ALARM_SOUND

        self._test_sound(ALARM_SOUND, "alarmu")

    def test_faction_sound(self):
        """Test faction sound playback."""
        # pylint: disable=import-outside-toplevel
        from evealert.manager.alertmanager import FACTION_SOUND

        self._test_sound(FACTION_SOUND, "frakcji")
