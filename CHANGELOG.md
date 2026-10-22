# Changelog

## [In Development] - Unreleased

<!--
Section Order:

### Added
### Fixed
### Changed
### Removed
-->

## [2.1.0] 2026-10-22

### Added

- **System name region (F3):** In config mode, F3 selects the part of the screen that shows the current solar system. The name is read with OCR (RapidOCR, offline) and enemy alarms are skipped while the player is in one of the systems entered in the new settings field "ignored systems" (names separated by commas). Faction alarms are not affected. If the name cannot be read, alarms stay on. Discord messages use the system name read from the screen; the "system name" setting is still the fallback name for Discord.
- Settings window opens over the main window

### Fixed

- **Threading:** The alert system runs in one worker thread with its own event loop per start. Stop/Start works repeatedly, and the GUI is no longer updated from background threads (random freezes and Tk errors)
- **Silent failures:** An unexpected error now stops the system with a message instead of leaving it "running" without detection
- **Webhook:** Errors in the "Alarm Reset" message no longer crash the alarm loop; requests no longer block the loop
- **Detection:** Duplicate detections from 90%/100% template variants are merged; single-colour templates no longer match every flat area
- **Settings:** Reading settings in the alert thread no longer rewrites `settings.json` or touches widgets; default settings are no longer mutated
- **Audio test:** Test buttons no longer freeze the GUI and use the volume slider
- Debug windows close reliably; the online status icon reference is correct
- Outdated test for negative region coordinates (allowed since [#51](https://github.com/Geuthur/EVE-Alert/issues/51))

### Changed

- **Performance:** Regions are captured and checked once per alarm check (every 2-3 s) instead of 10 times per second; the 10 Hz loop only runs while a debug window is open
- Screen capture reuses one `mss` instance; templates are prepared once
- `cv.groupRectangles` (removed in OpenCV 5) replaced by non-maximum suppression with a candidate limit
- A broken faction region only disables faction detection (with a message)
- Main window log keeps the last 500 lines
- Documentation in `docs/` translated from German to English

## [2.0.2] 2026-01-03

## Added
- Makefile System

### Changed
- removed negative error handler in some cases it needs to be negative see [#51](https://github.com/Geuthur/EVE-Alert/issues/51)

## [2.0.1] 2025-11-24

### Fixed

- **Resource loading:** Completely rewritten `get_resource_path()` — the application now always reads resources from the running executable. This ensures `img/` and `sound/` are consistently loaded in both development and distribution builds.
- **Sound handling:** Corrected `SOUND_FOLDER` in `evealert/constants.py` to `sound`, so custom WAV files like `alarm.wav` are properly located and played.

## [2.0.0] 2025-11-22

Big Thanks to [@Gotarr](https://github.com/Gotarr) for improving the whole EVE-Alert System with many QoL changes, fixes, optimations

### Added

- Codecov Report
- Discord Badge
- Release Badge
- Licence Badge
- Complete test infrastructure (pytest, pytest-asyncio, pytest-cov, pre-commit)
- 57 new unit and integration tests (test coverage: 65%)
- Real-time statistics and history system (alarm counter, session tracking, export to CSV/JSON)
- Configuration validation for all settings (regions, scales, timers, webhooks, audio)
- Central management of all constants (constants.py)
- Developer documentation and AI agent instructions (copilot-instructions.md)
- Sprint summaries and improvement plan in the docs folder

### Changed

- Updated Codecov action from `v4` to `v5`
- Refactoring: Exception hierarchy, import organization, code formatting (Black, isort)
- Type hints and docstrings for all modules
- Logging system with rotating file handler and module loggers
- Settings can now be changed at runtime (without restarting)
- Audio system: mono/stereo conversion, error handling, test buttons in the UI
- CI/CD: automated tests and coverage checks via GitHub Actions

### Fixed

- Various bugs in settings, vision, overlay, and audio
- Improved error and validation messages

### Removed

- Unnecessary and duplicate code sections
- Obsolete socket functions

## [1.0.1] 2025-06-12

### Fixed

- [#32](https://github.com/Geuthur/EVE-Alert-Opensource/issues/32)

## [1.0.0] 2025-03-30

### Changed

- Removed Socket System
  - The Socket System has been removed and we now use Discord Webhook to share Intel.
- Setting Loader
  - Missing Keys will be created.
- Update Dependencies
  - Open-CV Updated to 4.11.\*
  - ScreenInfo to 0.8.1
  - MSS to 10.0.0

### Added

- Discord System
  - All alarms are sent to a Discord webhook with the system name.
- dhooks-lite
  - Discord Webhook library

## [0.9.0] - 2025-01-08

### Changed

- Setting Manager
  - The settings manager has been refactored to improve the handling and organization of settings.
- Config Mode
  - The configuration mode has been optimized to respond more flexibly to changes.
- Refactor of the entire system
  - The system has been refactored to improve code readability and maintainability.
- Logger System
  - The logger system has been enhanced to capture more detailed information about errors, aiding in better troubleshooting.
- Alert Sound
  - The alert sound will not interrupt the program after an error occurs.

### Fixed

- EveLocal not closing with Window Close:
  - An issue was fixed where the EveLocal window would not properly close when the window's close button was clicked. This fix ensures that the window is now correctly closed when the user attempts to exit.
- Settings not reloaded if changed:
  - A bug where settings were not being reloaded after being modified has been resolved. Now, when changes are made to the settings, they will be properly reloaded, reflecting the new configuration.
- Vision not reloaded if changed:
  - A similar issue was addressed where vision settings (likely related to display or graphical configurations) were not reloaded after changes. This fix ensures that any changes to vision settings are immediately applied and reflected.
- Overlay Window not fitting exactly to the monitor resolution:
  - The overlay window was previously not aligning correctly with the monitor's resolution. This issue has been fixed, ensuring that the overlay window now correctly fits and scales to the screen size, providing a more accurate and consistent user interface.

### Added

- Propertys for each system
  - New properties have been added to manage and configure each system individually. This allows for more flexibility and control over system settings and their states.
- Socket System (Test)
  - A new socket system has been implemented for testing purposes. This enables communication between different components or systems, facilitating data exchange and interactions.
- Cleanup Functions
  - Cleanup functions have been introduced to improve resource management. These functions help remove unnecessary data, free up memory, and ensure the application remains efficient by handling cleanup tasks properly.
- Set changed flag in the menu:
  - The changed flag is now set to True whenever a modification is made to the menu settings. This helps track changes and triggers actions like warnings before exiting without saving.
- Buttons State
  - All buttons now have a state color to indicate when they are pressed. This visual cue helps users easily identify the current state of the buttons, improving the user interface and overall user experience by providing clearer feedback during interaction.
- Message Box System
  - Implemented a single-instance error message box to prevent multiple error windows from opening simultaneously.

## [0.5.0] - 2024-11-29

### Changed

- Settings for Regions now have a visual interface
- Setting Region now work per `Marquee Selection`
- Enemy & Faction now work seperately

### Fixed

- Faction Region can't be open if a error occurs [#15](https://github.com/Geuthur/EVE-Alert-Opensource/issues/15)
- In some Cases Multiple Monitors not work [#15](https://github.com/Geuthur/EVE-Alert-Opensource/issues/15) (Testing)
- Vision System not work if Detection Scale is Zero or below
- Images with Alpha Channel triggers Error [#15](https://github.com/Geuthur/EVE-Alert-Opensource/issues/15)
- It is not possible to switch Windows recognition off/on during sound playback
- Overlapping Overlay when F1 and F2 was pressed
- Background width is not correct

### Added

- Abort Option on Settings with `ESC`
- Faction Detection Scale
- Overlay System

### Removed

- Drop Color Mode Support
- Screenshot Mode

## [0.4.4] - 2024-11-23

### Changed

- print to logger in regionmanager
- Alarm Sound

### Fixed

- Faction Region can't be open if a error occurs [#15](https://github.com/Geuthur/EVE-Alert-Opensource/issues/15)

## [0.4.3] - 2024-10-18

### Added

- Dependency Requirment Info

### Changed

- Requirments
- Moved from PyAudio to sounddevice and soundfile
- Update Preview Video
- Update Window Installer

### Fixed

- Icon Bitmap Error on Linux [#9](https://github.com/Geuthur/EVE-Alert-Opensource/issues/9)

## [0.4.2] - 2024-10-18

### Added

- Window Installation Guide

### Fixed

- Window Installer not working correctly if executed as Admin

## [0.4.1b1] - 2024-05-24

### Added

- Cooldown Function with optional cooldowns
- Log Message Function
- Status Icon for Running Alert
- Log Textfield

### Fixed

- Program Blocking on some situations
- Alert Text appears after Error
- Performance Issues

### Changed

- Moved AlertAgent to Async
- AlertAgent now started via seperate Thread
- save_settings function moved to SettingsManager
- Moved Play Sound to one Function

### Removed

- Socket Functions, Maybe Later i will Implemend this..
- Log System Label
- Unused Code

## Full Changelog

[1.0.1]: https://github.com/Geuthur/eve-alert/compare/v1.0.0...v1.0.1 "1.0.1"
[2.0.0]: https://github.com/Geuthur/eve-alert/compare/v1.0.1...v2.0.0 "2.0.0"
[2.0.1]: https://github.com/Geuthur/eve-alert/compare/v2.0.0...v2.0.1 "2.0.1"
[2.0.2]: https://github.com/Geuthur/eve-alert/compare/v2.0.1...v2.0.2 "2.0.2"
[2.1.0]: https://github.com/Geuthur/eve-alert/compare/v2.0.2...v2.1.0 "2.1.0"
[in development]: https://github.com/Geuthur/eve-alert/compare/v2.1.0...HEAD "In Development"
[report any issues]: https://github.com/Geuthur/eve-alert/issues "report any issues"