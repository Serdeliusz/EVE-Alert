# EVE Alert - AI Agent Instructions

## Project Overview
EVE Alert is a Python desktop application that monitors EVE Online's local chat for enemy/neutral players using computer vision. It captures screen regions, performs OpenCV template matching, and triggers audio/Discord webhook alerts. Built with CustomTkinter GUI and asyncio-based alert system.

## Architecture

### Core Components
1. **AlertAgent** (`evealert/manager/alertmanager.py`) - Central asyncio-based monitoring system
   - `start()` launches one worker thread (`EVEAlertWorker`) with its own event loop
   - The worker runs two coroutines: `run()` (capture + detect + alarms every 2-3s) and
     `vision_debug_loop()` (refreshes the debug windows at 10 Hz only while they are open)
   - `stop()` cancels the worker's main task thread-safely and returns immediately
   - Manages cooldowns, audio playback, webhook notifications, and statistics

2. **Vision** (`evealert/tools/vision.py`) - OpenCV template matching engine
   - Supports multiple template images per detection type (e.g., `image_1_90%`, `image_1_100%`)
   - Templates are loaded and converted to contiguous BGR uint8 once in `__init__`
   - Uses `cv.TM_CCOEFF_NORMED` for matching with configurable thresholds
     (single-colour templates are compared by colour distance instead)
   - `detect()` raises `ScreenshotError`/`RegionSizeError`; `find()`/`find_faction()` log errors and return `[]`
   - Matches of all templates are grouped with non-maximum suppression (no `cv.groupRectangles`, which OpenCV 5 removed)
   - Debug mode shows live OpenCV windows ("Enemy Vision", "Faction Vision") with detection rectangles

3. **MainMenu** (`evealert/menu/main.py`) - CustomTkinter GUI
   - Manages overlay system for region selection (F1=alert, F2=faction, ESC=cancel)
   - Starts/stops the alert system via `self.alert.start()` / `self.alert.stop()`
   - `run_in_ui()` queues calls from other threads; `write_message()` and `open_error_window()` are thread-safe
   - Keyboard hotkeys (pynput thread) are handled in the GUI thread
   - Updates status icons every 1000ms via `check_status()`

4. **WindowCapture** (`evealert/tools/windowscapture.py`) - Screen capture using `mss`
   - Captures specific regions: `{"top": y1, "left": x1, "width": x2-x1, "height": y2-y1}`
   - Keeps one `mss` instance per thread (mss must not be shared between threads on Windows)
   - Returns a contiguous BGR array (alpha dropped)

### Data Flow
```
Screenshot (mss) → Vision.detect() → AlertAgent flags (enemy/faction)
  → alarm_detection() → play_sound() + webhook → statistics tracking
```

## Key Patterns & Conventions

### Threading & Asyncio Usage
- **Threads**: GUI thread (Tk), alert worker thread (asyncio loop), pynput keyboard listener thread
- **Event loop management**: A new event loop (and `asyncio.Lock`) is created in the worker thread on every start
- **GUI access**: Never touch Tk widgets outside the GUI thread - use `main.run_in_ui()` or `main.write_message()`
- **OpenCV windows**: Created and closed only in the worker thread
- **Settings in the worker**: Use `SettingMenu.read_settings()` (no file writes, no widget access), not `load_settings()`
- **Errors**: An unexpected error stops the worker with a visible message; never swallow it silently
- **Sleep intervals**: Main loop 2-3s random interval; debug windows refresh every 0.1s while open

### Settings System
- Settings stored in `evealert/settings.json` with structure:
  ```json
  {
    "alert_region_1": {"x": 100, "y": 100},
    "alert_region_2": {"x": 300, "y": 300},
    "detectionscale": {"value": 90},
    "cooldown_timer": {"value": 60},
    "volume": {"value": 100},
    "server": {"webhook": "https://...", "mute": false}
  }
  ```
- **ALWAYS** validate settings with `ConfigValidator.validate_settings_dict()` before use
- The worker reloads settings when `self.main.menu.setting.is_changed` is True (it clears the flag first)

### Audio System
- Convert mono to stereo: `np.stack([data, data], axis=-1)` if `data.ndim == 1`
- Apply volume: `(data * self.volume).astype('int16')` (volume is 0.0-1.0)
- Uses sounddevice+soundfile: `sf.read()` then `sd.play()`
- Implements trigger limiting: max 3 plays before cooldown

### Template Image Naming
- Alert images: `evealert/img/image_1.png`, `image_1_90%`, `image_2.png`, etc.
- Faction images: `evealert/img/faction_1.png`, `faction_1_90%`, etc.
- Loaded via list comprehension filtering by prefix (`ALERT_IMAGE_PREFIX`, `FACTION_IMAGE_PREFIX`)

### Exception Hierarchy
All custom exceptions inherit from `EVEAlertException`:
- `ScreenshotError` - Screenshot capture failures
- `RegionSizeError` - Detection region smaller than template
- `ValidationError` - Settings validation failures
- `AudioError` - Sound playback issues

### Logging Structure
- Separate loggers: `alert`, `menu`, `main`, `tools`, `validator`
- Rotating file handler: 5MB per file, 3 backups
- Format: `%(asctime)s [%(levelname)-8s] %(name)-12s %(funcName)-20s:%(lineno)-4d - %(message)s`

## Development Workflows

### Running the Application
```powershell
python main.py
```

### Running Tests
```powershell
# All tests
pytest

# With coverage report
pytest --cov=evealert --cov-report=html

# Specific test file
pytest tests/test_vision.py

# Single test
pytest tests/test_alertmanager.py::TestAlertAgent::test_alarm_detection
```

### Pre-commit Checks
Project uses pre-commit hooks for code quality:
```powershell
# Install hooks
pre-commit install

# Run all checks
pre-commit run --all-files

# Run specific check
pre-commit run black
```

### Building Executable
Uses PyInstaller (configured in `pyproject.toml`):
```powershell
pyinstaller main.py --onefile --windowed --icon=evealert/img/icon.ico
```

## Testing Patterns

### Mocking GUI Components
Always mock `MainMenu` in tests:
```python
self.mock_main = MagicMock()
self.mock_main.write_message = MagicMock()
self.mock_main.menu.setting.read_settings.return_value = test_settings
```

### Testing Async Code
Use `asyncio.run()` for coroutine tests:
```python
async def async_test():
    await agent.alarm_detection("Test", sound_file, "Enemy")


asyncio.run(async_test())
```

### Testing Vision
Create test images with OpenCV:
```python
haystack = np.zeros((100, 100, 3), dtype=np.uint8)
needle_paths = ["test_image.png"]
vision = Vision(needle_paths)
result = vision.find(haystack, threshold=90)
```

## CI/CD Pipeline
GitHub Actions workflow (`.github/workflows/python-package.yml`):
1. **Pre-commit checks** - Linting, formatting (black, ruff)
2. **Test matrix** - Python 3.10, 3.11, 3.12, 3.13 on Ubuntu
3. **Coverage reporting** - Codecov integration
4. **Build executable** - PyInstaller Windows build on release

## Important Constraints

### Display Scaling
Application REQUIRES 100% Windows display scaling for accurate template matching. Different scalings need separate template images (e.g., `image_1_90%` for 90% scaling).

### Region Validation
- Regions must be at least 10x10 pixels
- x1 < x2, y1 < y2
- Coordinates can be negative (monitors left of / above the primary, see #51)
- Detection region must be larger than template images

### Webhook Behavior
- Discord webhooks have 5-second cooldown (`WEBHOOK_COOLDOWN`)
- Sent from an executor thread so a slow request never blocks the alarm loop; errors are logged
- Only sent for "Enemy" alarms, not "Faction"
- Sends "Alarm Reset" message when enemy clears

## Common Pitfalls

1. **Don't touch Tk widgets from the worker thread** - Use `run_in_ui()`
2. **Don't create `mss` or OpenCV windows in another thread** - They belong to the worker thread
3. **Check settings validation before loading** - Use `ConfigValidator.validate_settings_dict()`
4. **Handle audio channel conversion** - Mono must be converted to stereo
5. **Use absolute paths** - `get_resource_path()` for bundled resources
6. **Test with multiple template images** - Vision accepts lists of image paths
7. **Respect cooldown timers** - Both sound and webhook have separate cooldowns

## Key Files for Understanding
- `evealert/manager/alertmanager.py` - Main alert logic and asyncio orchestration
- `evealert/tools/vision.py` - Template matching implementation
- `evealert/constants.py` - All configurable constants and thresholds
- `evealert/settings/validator.py` - Settings validation logic
- `tests/test_alertmanager.py` - Shows proper testing patterns
