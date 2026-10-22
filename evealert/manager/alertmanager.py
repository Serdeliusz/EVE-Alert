import asyncio
import logging
import os
import random
import threading
import time
from typing import TYPE_CHECKING

import numpy as np
import sounddevice as sd
import soundfile as sf

from evealert.constants import (
    ALARM_SOUND_FILE,
    ALARM_TYPE_NAMES,
    ALERT_IMAGE_PREFIX,
    ALERT_STOP_TIMEOUT,
    AUDIO_CHANNELS,
    DEFAULT_COOLDOWN_TIMER,
    FACTION_IMAGE_PREFIX,
    FACTION_SOUND_FILE,
    IMG_FOLDER,
    MAIN_CHECK_SLEEP_MAX,
    MAIN_CHECK_SLEEP_MIN,
    MAX_SOUND_TRIGGERS,
    SOUND_FOLDER,
    VISION_IDLE_INTERVAL,
    VISION_SLEEP_INTERVAL,
    WEBHOOK_COOLDOWN,
    WEBHOOK_TIMEOUT,
)
from evealert.exceptions import EVEAlertException
from evealert.settings.helper import get_resource_path
from evealert.settings.validator import ConfigValidator
from evealert.statistics import AlarmStatistics
from evealert.tools.systemname import (
    SystemNameReader,
    extract_system_name,
    find_matching_name,
    parse_names,
)
from evealert.tools.vision import Vision
from evealert.tools.windowscapture import WindowCapture

if TYPE_CHECKING:
    from evealert.menu.main import MainMenu

# Sound file paths
ALARM_SOUND = get_resource_path(f"{SOUND_FOLDER}/{ALARM_SOUND_FILE}")
FACTION_SOUND = get_resource_path(f"{SOUND_FOLDER}/{FACTION_SOUND_FILE}")
IMG_FOLDER_PATH = get_resource_path(IMG_FOLDER)

ALERT_FILES = sorted(
    os.path.join(IMG_FOLDER_PATH, filename)
    for filename in os.listdir(IMG_FOLDER_PATH)
    if filename.startswith(ALERT_IMAGE_PREFIX)
)
FACTION_FILES = sorted(
    os.path.join(IMG_FOLDER_PATH, filename)
    for filename in os.listdir(IMG_FOLDER_PATH)
    if filename.startswith(FACTION_IMAGE_PREFIX)
)

logger = logging.getLogger("alert")


class AlertAgent:  # pylint: disable=too-many-public-methods
    """Alert Agent for EVE Online local chat monitoring.

    This class manages the complete alert system including:
    - Screenshot capture and analysis
    - Enemy and faction detection via template matching
    - Audio alerts with cooldown management
    - Discord webhook notifications
    - Vision debug windows

    Threading model:
        The GUI runs in the main thread. ``start()`` launches one worker
        thread that owns its own asyncio event loop. Everything that touches
        the screen capture, OpenCV windows or audio runs in that worker
        thread. The worker never touches Tk widgets directly: it uses the
        thread-safe ``MainMenu.write_message`` and ``MainMenu.run_in_ui``.
        ``stop()`` can be called from any thread; it cancels the worker's
        main task and returns immediately.
    """

    def __init__(self, main: "MainMenu"):
        """Initialize the Alert Agent.

        Args:
            main: Reference to the MainMenu instance
        """
        self.main = main
        self.wincap = WindowCapture(self.main)
        self.alert_vision = Vision(ALERT_FILES)
        self.alert_vision_faction = Vision(FACTION_FILES)

        # Main Settings
        self.running = False
        self.check = False

        # Prevents multiple alarm loops from running at the same time
        self.lock = asyncio.Lock()

        # Worker thread state (guarded by _state_lock)
        self._state_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._main_task: asyncio.Task | None = None
        self._stop_requested = threading.Event()

        # Region settings (filled by load_settings)
        self.x1 = self.y1 = self.x2 = self.y2 = 0
        self.x1_faction = self.y1_faction = self.x2_faction = self.y2_faction = 0
        self.detection = 90
        self.detection_faction = 90
        self.system_name = ""  # name used in Discord messages
        self.ignored_systems = ""  # comma separated, enemy alarms skipped there
        # System name region (F3); all zeros = not set
        self.x1_system = self.y1_system = self.x2_system = self.y2_system = 0

        # Location (system name read with OCR from the F3 region)
        self.system_reader = SystemNameReader()
        self.system_check_enabled = False
        self.current_system = ""  # name read from the screen ("" = unknown)
        self.in_ignored_system: str | None = None  # matching name from settings

        # Vision Settings
        self.enemy = False
        self.faction = False
        self.faction_enabled = True

        # Alarm Settings
        self.cooldown_timers = {}
        self.cooldowntimer = DEFAULT_COOLDOWN_TIMER
        self.alarm_detected = False
        self.mute = False
        self.volume = 1.0  # Default volume: 100% (0.0 to 1.0)

        # Webhook Settings
        self.webhook_cooldown_timer = 0
        self.webhook_sent = False

        # Sound Settings
        self.p = sd
        self.alarm_trigger_counts = {}
        self.max_sound_triggers = MAX_SOUND_TRIGGERS
        self.currently_playing_sounds = {}

        # Statistics
        self.statistics = AlarmStatistics()

        self.load_settings()
        self._validate_audio_files()

    def _validate_audio_files(self):
        """Validate that required audio files exist."""
        valid_alarm, error_alarm = ConfigValidator.validate_audio_file(
            ALARM_SOUND, "Dźwięk alarmu"
        )
        valid_faction, error_faction = ConfigValidator.validate_audio_file(
            FACTION_SOUND, "Dźwięk frakcji"
        )

        if not valid_alarm:
            logger.warning(error_alarm)
            self.main.write_message(f"Uwaga: {error_alarm}", "red")

        if not valid_faction:
            logger.warning(error_faction)
            self.main.write_message(f"Uwaga: {error_faction}", "red")

    @property
    def is_running(self) -> bool:
        return self.running

    @property
    def is_alive(self) -> bool:
        """Returns True while the worker thread exists."""
        thread = self._thread
        return thread is not None and thread.is_alive()

    @property
    def is_alarm(self) -> bool:
        return self.alarm_detected

    @property
    def is_enemy(self) -> bool:
        return self.enemy

    @property
    def is_faction(self) -> bool:
        return self.faction

    def get_statistics(self) -> AlarmStatistics:
        """Get alarm statistics tracker.

        Returns:
            AlarmStatistics instance with current statistics
        """
        return self.statistics

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Start the alert system in a background thread.

        Must be called from the GUI thread. Returns immediately.

        Returns:
            True if the worker thread was started
        """
        if self.is_alive:
            if self._stop_requested.is_set():
                self.main.write_message(
                    "System: EVE Alert jeszcze się zatrzymuje. Spróbuj za chwilę."
                )
            else:
                self.main.write_message("System: EVE Alert już działa.")
            return False

        if not self.load_settings():
            self.main.write_message(
                "System: popraw ustawienia i uruchom ponownie.", "red"
            )
            return False

        if not self.alert_vision.has_templates:
            self.main.write_message(
                "System: brak obrazków alarmu w folderze img.", "red"
            )
            return False

        self.check = True
        self.faction_enabled = self.alert_vision_faction.has_templates
        self._stop_requested.clear()
        self.running = True
        self._thread = threading.Thread(
            target=self._thread_main, name="EVEAlertWorker", daemon=True
        )
        self._thread.start()
        self.main.write_message("System: EVE Alert uruchomiony.", "green")
        return True

    def stop(self) -> None:
        """Request the worker thread to stop. Safe to call from any thread."""
        self._stop_requested.set()
        with self._state_lock:
            loop, task = self._loop, self._main_task
            if loop is not None and task is not None and not loop.is_closed():
                loop.call_soon_threadsafe(task.cancel)

    def clean_up(self) -> None:
        """Stop the worker thread and wait for it (used on application exit)."""
        self.stop()
        thread = self._thread
        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=ALERT_STOP_TIMEOUT)
            if thread.is_alive():
                logger.warning("Alert thread did not stop in time.")

    def _thread_main(self) -> None:
        """Entry point of the worker thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # asyncio primitives belong to one event loop, and every start
        # creates a new loop, so the lock is created fresh as well.
        self.lock = asyncio.Lock()
        try:
            with self._state_lock:
                self._loop = loop
                self._main_task = loop.create_task(self._main())
                if self._stop_requested.is_set():
                    self._main_task.cancel()
            loop.run_until_complete(self._main_task)
        except asyncio.CancelledError:
            logger.debug("Alert system cancelled.")
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Alert system crashed: %s", e)
            self.main.write_message(
                "System: EVE Alert zatrzymany z powodu błędu. Szczegóły w logach.",
                "red",
            )
        finally:
            with self._state_lock:
                self._main_task = None
                self._loop = None
            self._shutdown_loop(loop)
            self._release_resources()
            self.running = False
            self.main.run_in_ui(self._on_stopped)

    @staticmethod
    def _shutdown_loop(loop: asyncio.AbstractEventLoop) -> None:
        """Cancel leftover tasks and close the event loop."""
        try:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.debug("Error while shutting down the event loop: %s", e)
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    def _release_resources(self) -> None:
        """Release resources owned by the worker thread."""
        # OpenCV windows must be closed by the thread that created them.
        self.alert_vision.clean_up()
        self.alert_vision_faction.clean_up()
        self.wincap.close()
        self.currently_playing_sounds = {}
        self.alarm_trigger_counts = {}
        self.cooldown_timers = {}
        self.enemy = False
        self.faction = False
        self.alarm_detected = False
        self.webhook_sent = False
        self.current_system = ""
        self.in_ignored_system = None

    def _on_stopped(self) -> None:
        """Update the GUI after the worker thread ended (GUI thread)."""
        self.main.update_alert_button()
        self.main.update_faction_button()
        self.main.write_message("System: EVE Alert zatrzymany.", "green")

    async def _main(self) -> None:
        """Run the alarm loop and the debug window loop together."""
        tasks = [
            asyncio.create_task(self.run(), name="alarm-loop"),
            asyncio.create_task(self.vision_debug_loop(), name="vision-debug-loop"),
        ]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                # Re-raise errors from the finished task
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def load_settings(self) -> bool:
        """Read and validate settings from disk.

        This method never touches GUI widgets, so it is safe to call from
        the worker thread.

        Returns:
            True if valid settings were loaded
        """
        settings = self.main.menu.setting.read_settings()
        if not settings:
            return False

        is_valid, errors = ConfigValidator.validate_settings_dict(settings)
        if not is_valid:
            error_msg = "Configuration validation failed:\n" + "\n".join(errors)
            logger.error(error_msg)
            self.main.write_message("Błędne ustawienia, szczegóły w logach.", "red")
            for error in errors:
                self.main.write_message(f"  - {error}", "red")
            return False

        try:
            self.x1 = int(settings["alert_region_1"]["x"])
            self.y1 = int(settings["alert_region_1"]["y"])
            self.x2 = int(settings["alert_region_2"]["x"])
            self.y2 = int(settings["alert_region_2"]["y"])
            self.x1_faction = int(settings["faction_region_1"]["x"])
            self.y1_faction = int(settings["faction_region_1"]["y"])
            self.x2_faction = int(settings["faction_region_2"]["x"])
            self.y2_faction = int(settings["faction_region_2"]["y"])
            self.detection = int(settings["detectionscale"]["value"])
            self.detection_faction = int(settings["faction_scale"]["value"])
            self.cooldowntimer = int(settings["cooldown_timer"]["value"])
            self.volume = settings.get("volume", {}).get("value", 100) / 100.0
            server = settings.get("server", {})
            self.mute = bool(server.get("mute", False))
            self.system_name = str(server.get("system", ""))
            self.ignored_systems = str(server.get("ignored_systems", ""))
            system_region_1 = settings.get("system_region_1", {})
            system_region_2 = settings.get("system_region_2", {})
            self.x1_system = int(system_region_1.get("x", 0))
            self.y1_system = int(system_region_1.get("y", 0))
            self.x2_system = int(system_region_2.get("x", 0))
            self.y2_system = int(system_region_2.get("y", 0))
        except (KeyError, TypeError, ValueError) as e:
            logger.exception("Invalid settings: %s", e)
            self.main.write_message("Ustawienia: błędny plik ustawień.", "red")
            return False

        # A new faction region gets a new chance after it was disabled
        self.faction_enabled = self.alert_vision_faction.has_templates
        # The same for the system name region
        self.system_check_enabled = self.has_system_region
        self.system_reader.reset()
        return True

    @property
    def has_system_region(self) -> bool:
        """Returns True if a system name region (F3) is set."""
        return any((self.x1_system, self.y1_system, self.x2_system, self.y2_system))

    def _reload_settings_if_changed(self) -> None:
        """Reload settings in the worker thread when the GUI changed them."""
        setting_menu = self.main.menu.setting
        if setting_menu.is_changed:
            # Clear the flag before reading so a change made while reading
            # is not lost.
            setting_menu.changed = False
            if self.load_settings():
                self.main.write_message("Ustawienia: wczytano.", "green")
            else:
                self.main.write_message(
                    "Ustawienia: zostają poprzednie ustawienia.", "yellow"
                )

    # ------------------------------------------------------------------
    # Vision
    # ------------------------------------------------------------------

    def set_vision(self) -> None:
        """Toggle the enemy debug window (GUI thread)."""
        if self.is_running:
            self.alert_vision.debug_mode = not self.alert_vision.debug_mode
            self.main.update_alert_button()

    def set_vision_faction(self) -> None:
        """Toggle the faction debug window (GUI thread)."""
        if self.is_running:
            self.alert_vision_faction.debug_mode_faction = (
                not self.alert_vision_faction.debug_mode_faction
            )
            self.main.update_faction_button()

    def _capture_alert_region(self):
        screenshot, _ = self.wincap.get_screenshot_value(
            self.y1, self.x1, self.x2, self.y2
        )
        return screenshot

    def _capture_faction_region(self):
        screenshot, _ = self.wincap.get_screenshot_value(
            self.y1_faction, self.x1_faction, self.x2_faction, self.y2_faction
        )
        return screenshot

    def _capture_system_region(self):
        screenshot, _ = self.wincap.get_screenshot_value(
            self.y1_system, self.x1_system, self.x2_system, self.y2_system
        )
        return screenshot

    def _disable_system_check(self, reason: str) -> None:
        """Turn off reading the system name (alarms then always work)."""
        self.system_check_enabled = False
        self.current_system = ""
        self.in_ignored_system = None
        self.main.write_message(
            f"Nazwa systemu: odczyt wyłączony ({reason}). "
            "Alarmy o wrogach działają wszędzie. Zaznacz obszar ponownie (F3).",
            "yellow",
        )

    def update_location(self) -> None:
        """Read the system name and check it against the settings.

        Sets ``current_system`` and ``in_ignored_system``. Never raises: if
        the name cannot be read, the alarms stay on.
        """
        if not self.system_check_enabled:
            self.in_ignored_system = None
            return

        screenshot = self._capture_system_region()
        if screenshot is None:
            self._disable_system_check("nie udało się zrobić zrzutu obszaru")
            return

        text = self.system_reader.read(screenshot)
        if text is None:
            self._disable_system_check(
                f"OCR niedostępny: {self.system_reader.error or 'błąd odczytu'}"
            )
            return

        previous_system = self.current_system
        previous_ignored = self.in_ignored_system
        self.current_system = extract_system_name(text)
        self.in_ignored_system = find_matching_name(
            text, parse_names(self.ignored_systems)
        )

        if self.current_system != previous_system:
            if self.current_system:
                self.main.write_message(f"Lokalizacja: {self.current_system}")
            else:
                self.main.write_message(
                    "Lokalizacja: nie odczytano nazwy systemu – alarmy działają.",
                    "yellow",
                )
        if self.in_ignored_system != previous_ignored:
            if self.in_ignored_system:
                self.main.write_message(
                    f"Jesteś w {self.in_ignored_system} – alarmy o wrogach "
                    "są tu pomijane.",
                    "yellow",
                )
            elif previous_ignored:
                self.main.write_message(
                    f"Opuściłeś {previous_ignored} – alarmy o wrogach włączone.",
                    "green",
                )

    @property
    def alert_system_name(self) -> str:
        """System name used in messages: read from the screen, else from settings."""
        if self.current_system:
            return self.current_system
        return self.system_name

    async def vision_check(self) -> None:
        """Validate that screenshot capture works for configured alert region."""
        self.check = self._capture_alert_region() is not None
        if not self.check:
            self.main.write_message("Błędne ustawienia obszaru alarmu.", "red")

    def update_detection(self) -> bool:
        """Capture both regions and update the enemy and faction flags.

        Returns:
            False if the alert region cannot be checked. The alert system
            must then stop, because it could not warn the player.
        """
        screenshot = self._capture_alert_region()
        if screenshot is None:
            self.main.write_message(
                "Błędne ustawienia: nie udało się zrobić zrzutu obszaru alarmu.",
                "red",
            )
            return False
        try:
            points, _ = self.alert_vision.detect(screenshot, self.detection, "Enemy")
        except EVEAlertException as e:
            logger.error("Enemy detection failed: %s", e)
            self.main.write_message(str(e), "red")
            return False
        self.enemy = bool(points)

        if self.faction_enabled:
            self.faction = self._detect_faction()
        else:
            self.faction = False
        return True

    def _detect_faction(self) -> bool:
        """Run faction detection. Disables it (with a message) on errors."""
        screenshot = self._capture_faction_region()
        error = None
        if screenshot is None:
            error = "nie udało się zrobić zrzutu obszaru frakcji"
        else:
            try:
                points, _ = self.alert_vision_faction.detect(
                    screenshot, self.detection_faction, "Faction"
                )
                return bool(points)
            except EVEAlertException as e:
                logger.error("Faction detection failed: %s", e)
                error = str(e)

        self.faction_enabled = False
        self.main.write_message(
            f"Wykrywanie frakcji wyłączone: {error}. Sprawdź obszar frakcji.",
            "yellow",
        )
        return False

    async def vision_debug_loop(self) -> None:
        """Refresh the debug windows while they are enabled.

        The windows are created and closed in the worker thread, because
        OpenCV windows must be handled by a single thread.
        """
        while True:
            active = False

            vision = self.alert_vision
            if vision.debug_mode:
                active = True
                screenshot = self._capture_alert_region()
                if screenshot is not None:
                    vision.find(screenshot, self.detection)
                if not vision.debug_mode:
                    # find() disabled the window after an error
                    self.main.run_in_ui(self.main.update_alert_button)
            else:
                vision.close_debug_window("Enemy")

            faction_vision = self.alert_vision_faction
            if faction_vision.debug_mode_faction:
                active = True
                screenshot = self._capture_faction_region()
                if screenshot is not None:
                    faction_vision.find_faction(screenshot, self.detection_faction)
                if not faction_vision.debug_mode_faction:
                    self.main.run_in_ui(self.main.update_faction_button)
            else:
                faction_vision.close_debug_window("Faction")

            await asyncio.sleep(
                VISION_SLEEP_INTERVAL if active else VISION_IDLE_INTERVAL
            )

    # ------------------------------------------------------------------
    # Alarms
    # ------------------------------------------------------------------

    async def _execute_webhook(self, message: str) -> bool:
        """Send a webhook message without blocking the event loop."""
        webhook = self.main.webhook
        if not webhook:
            return False
        loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, webhook.execute, message),
                WEBHOOK_TIMEOUT,
            )
            return True
        except asyncio.CancelledError:
            raise
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error sending webhook: %s", e)
            return False

    async def reset_alarm(self, alarm_type: str) -> None:
        """Reset alarm counters and cooldown for the given alarm type."""
        if alarm_type in self.alarm_trigger_counts:
            self.alarm_trigger_counts[alarm_type] = 0
            self.cooldown_timers[alarm_type] = 0

        if alarm_type == "Enemy" and self.webhook_sent:
            self.webhook_sent = False
            system_name = self.alert_system_name
            if system_name:
                message = f"Koniec alarmu: {system_name}"
            else:
                message = "Koniec alarmu"
            await self._execute_webhook(message)

    async def alarm_detection(
        self, alarm_text: str, sound: str = ALARM_SOUND, alarm_type: str = "Enemy"
    ) -> None:
        """Trigger an alarm with text message, sound, and webhook notification."""
        self.main.write_message(
            f"{alarm_text}",
            "red",
        )
        # Track alarm in statistics
        self.statistics.add_alarm(alarm_type)
        await self.play_sound(sound, alarm_type)
        await self.send_webhook_message(alarm_type)

    async def send_webhook_message(self, alarm_type: str) -> None:
        """Send webhook notification for enemy alarms with cooldown."""
        current_time = time.time()
        # Ensure to limit the webhook sending to once per WEBHOOK_COOLDOWN
        if current_time < self.webhook_cooldown_timer:
            logger.info("Webhook is in cooldown period. Message not sent.")
            return

        if self.main.webhook and alarm_type == "Enemy" and self.webhook_sent is False:
            self.webhook_cooldown_timer = current_time + WEBHOOK_COOLDOWN
            system_name = self.alert_system_name
            if system_name:
                message = f"Wróg w {system_name}!"
            else:
                message = "Wróg w systemie!"
            if await self._execute_webhook(message):
                self.webhook_sent = True

    async def play_sound(self, sound: str, alarm_type: str) -> None:
        """Play alarm sound with trigger limits and cooldown management."""
        if self.mute:
            return

        # Initialize counter and cooldown timer if not present
        if alarm_type not in self.alarm_trigger_counts:
            self.alarm_trigger_counts[alarm_type] = 0
        if alarm_type not in self.cooldown_timers:
            self.cooldown_timers[alarm_type] = 0

        # Check cooldown timer
        current_time = time.time()
        if current_time < self.cooldown_timers[alarm_type]:
            self.main.write_message(
                f"Dźwięk ({ALARM_TYPE_NAMES.get(alarm_type, alarm_type)}): trwa przerwa.",
                "yellow",
            )
            return

        # Increment the counter
        self.alarm_trigger_counts[alarm_type] += 1

        # Check if the alarm has been triggered three times
        if self.alarm_trigger_counts[alarm_type] > self.max_sound_triggers:
            self.cooldown_timers[alarm_type] = current_time + self.cooldowntimer
            self.alarm_trigger_counts[alarm_type] = 0
            self.main.write_message(
                f"Dźwięk ({ALARM_TYPE_NAMES.get(alarm_type, alarm_type)}): przerwa na {self.cooldowntimer} s.",
                "yellow",
            )
            return

        if alarm_type not in self.currently_playing_sounds:
            self.currently_playing_sounds[alarm_type] = True
            try:
                # Read audio data with soundfile
                data, samplerate = sf.read(sound, dtype="int16")

                # Check data shape and adjust channels if necessary
                if data.ndim == 1:
                    # Convert Mono -> Stereo
                    data = np.stack([data, data], axis=-1)
                elif data.ndim == 2 and data.shape[1] == 1:
                    # (N, 1) -> (N, AUDIO_CHANNELS)
                    data = np.repeat(data, AUDIO_CHANNELS, axis=1)

                # Apply volume
                data_with_volume = (data * self.volume).astype("int16")

                # Play the audio data
                sd.play(data_with_volume, samplerate)
                await asyncio.sleep(
                    len(data) / samplerate
                )  # Wait for the sound to finish
            except asyncio.CancelledError:
                raise
            except Exception as e:  # pylint: disable=broad-exception-caught
                if self.alarm_trigger_counts[alarm_type] <= 1:
                    self.main.open_error_window(
                        "Błąd odtwarzania dźwięku. Szczegóły w logach."
                    )
                logger.exception("Error Playing Sound: %s", e)
            finally:
                self.currently_playing_sounds.pop(alarm_type, None)

    async def run(self) -> None:
        """Main alert checking loop.

        Enemy alarms are skipped while the player is in a system from the
        settings ("Nazwa systemu"), read from the F3 region. Faction alarms
        are not affected.

        Returns when the alert region can no longer be checked. Any other
        unexpected error is raised and stops the whole system with a message,
        so the player never believes they are protected when they are not.
        """
        async with self.lock:
            while True:
                self._reload_settings_if_changed()

                # Reset alarm status
                self.alarm_detected = False

                if not self.update_detection():
                    return

                # OCR runs only when the region image changed, so this is
                # usually just one screenshot comparison.
                self.update_location()
                if self.enemy and self.in_ignored_system:
                    self.main.write_message(
                        f"Wróg w Local – pominięty ({self.in_ignored_system}).",
                    )
                    self.enemy = False

                if self.faction:
                    self.alarm_detected = True
                    await self.alarm_detection(
                        "Spawn frakcji!", FACTION_SOUND, "Faction"
                    )
                if self.enemy:
                    self.alarm_detected = True
                    await self.alarm_detection("Wróg w Local!", ALARM_SOUND, "Enemy")

                # Reset alarms that are no longer detected
                if not self.faction:
                    await self.reset_alarm("Faction")
                if not self.enemy:
                    await self.reset_alarm("Enemy")

                sleep_time = random.uniform(MAIN_CHECK_SLEEP_MIN, MAIN_CHECK_SLEEP_MAX)
                self.main.write_message(
                    f"Następne sprawdzenie za {sleep_time:.2f} s...",
                )
                await asyncio.sleep(sleep_time)
