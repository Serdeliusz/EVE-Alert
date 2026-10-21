# EVE-Alert Improvement Plan

## Project Overview

Systematic improvement of the EVE-Alert system for better performance, stability and maintainability.

______________________________________________________________________

## Phase 1: Basic Stability & Dependencies ⚡

### 1.1 Dependency Synchronization

**Priority:** HIGH | **Effort:** 1h | **Status:** ✅ Completed

- [x] Synchronize `requirements.txt` and `pyproject.toml`
  - mss: 10.0.0 (synchronized)
  - opencv-python: 4.11.0.86 (synchronized)
  - screeninfo: 0.8.1 (synchronized)
  - CTkMessagebox added to pyproject.toml
- [x] Dependencies sorted alphabetically
- [x] Both files now use identical versions

**Expected result:** ✅ Consistent dependencies, no version conflicts

______________________________________________________________________

### 1.2 Error Handling & Validation

**Priority:** HIGH | **Effort:** 3h | **Status:** ✅ Completed

- [x] Configuration validation implemented at startup
  - Validate region coordinates (x1 < x2, y1 < y2)
  - Check detection scale range (0-100)
  - Validate webhook URL format
  - Check that audio files exist
- [x] Custom exception classes created for different error types
  - EVEAlertException (base)
  - ConfigurationError, ValidationError
  - AudioError, WebhookError
- [x] ConfigValidator class with comprehensive validation methods
- [x] Unit tests for validation created (test_validator.py)
- [x] Audio file validation when the AlertAgent starts

**Expected result:** ✅ More robust application, fewer crashes

______________________________________________________________________

## Phase 2: Performance Optimization 🚀

### 2.1 Screenshot Processing Optimization

**Priority:** MEDIUM | **Effort:** 2h | **Status:** ✅ Completed

- [x] Reduced repeated image conversions
  - `windowscapture.py`: returns a NumPy array directly
  - Removed unnecessary PIL Image conversion
- [x] Remove the alpha channel only once
- [x] Type hints added for WindowCapture
- [x] Improved error handling with logging

**Expected result:** ✅ 15-20% faster screenshot processing

______________________________________________________________________

### 2.2 Vision Thread Optimization

**Priority:** MEDIUM | **Effort:** 2h | **Status:** ✅ Partially completed

- [x] Sleep times defined as constants (VISION_SLEEP_INTERVAL)
- [x] Template matching constants extracted
- [ ] Evaluate unnecessary locks and remove them if possible
- [ ] Evaluate batch processing of multiple needle images

**Expected result:** 🔄 Lower CPU load, smoother UI (in progress)

______________________________________________________________________

### 2.3 Eliminate Magic Numbers

**Priority:** LOW | **Effort:** 1h | **Status:** ✅ Completed

- [x] Constants file created (`evealert/constants.py`)
  - Sleep times (MAIN_CHECK_SLEEP_MIN/MAX, VISION_SLEEP_INTERVAL)
  - Cooldown values (DEFAULT_COOLDOWN_TIMER, WEBHOOK_COOLDOWN)
  - Max sound triggers (MAX_SOUND_TRIGGERS)
  - Detection thresholds (DETECTION_THRESHOLD_MIN/MAX)
  - UI dimensions (WINDOW_WIDTH/HEIGHT)
  - OpenCV parameters (CV_RECTANGLE_THICKNESS, CV_LINE_TYPE, CV_DETECTION_COLOR)
  - Audio constants (AUDIO_CHANNELS)
  - File paths and prefixes
- [x] All hardcoded values replaced with constants in:
  - alertmanager.py
  - vision.py
  - main.py

**Expected result:** ✅ Better maintainability, easy adjustment

______________________________________________________________________

## Phase 3: Code Quality & Maintainability 📝

### 3.1 Complete Type Hints

**Priority:** MEDIUM | **Effort:** 2h | **Status:** ✅ Completed

- [x] Type hints added for AlertAgent properties
- [x] Type hints for core methods (start, stop, load_settings)
- [x] Type hints for WindowCapture complete
- [x] Type hints for ConfigValidator complete
- [x] Type hints for MainMenu and all GUI classes
- [x] Type hints for ConfigModeMenu complete
- [x] Type hints for OverlaySystem with Optional types
- [x] Type hints for helper.py
- [x] Return types added for 45+ methods
- [ ] mypy integration for type checking (optional)

**Expected result:** ✅ Better IDE support, ~90% type coverage

______________________________________________________________________

### 3.2 Improve Logging

**Priority:** LOW | **Effort:** 1h | **Status:** ✅ Completed (Sprint 2)

- [x] Use structured log levels consistently
  - DEBUG for vision details
  - INFO for normal events
  - WARNING for recoverable errors
  - ERROR for critical errors
- [x] Log rotation implemented (5MB, 3 backups)
- [ ] Optionally log performance metrics

**Expected result:** ✅ Better debugging and troubleshooting

______________________________________________________________________

### 3.3 Complete Documentation

**Priority:** HIGH | **Effort:** 2h | **Status:** ✅ Completed

- [x] All comments switched to English
- [x] Comprehensive docstrings for all classes
- [x] Method-level docstrings with Args/Returns
- [x] Examples in docstrings where helpful
- [x] Google style format used throughout
- [x] ~95% docstring coverage reached

**Expected result:** ✅ Professional documentation, easy onboarding

______________________________________________________________________

## Phase 4: New Features & Improvements ✨

### 4.1 Runtime Configuration

**Priority:** MEDIUM | **Effort:** 3h | **Status:** ⏳ Pending

- [ ] Make settings adjustable at runtime
  - Change detection scale live
  - Adjust cooldown timer
  - Control sound volume
- [ ] "Apply Settings" without restart
- [ ] Real-time settings validation

**Expected result:** Better user experience

______________________________________________________________________

### 4.2 Multi-Monitor Support

**Priority:** LOW | **Effort:** 4h | **Status:** ⏳ Pending

- [ ] Monitor selection in settings
- [ ] Coordinates relative to the selected monitor
- [ ] Automatic monitor detection
- [ ] Multi-monitor overlay system

**Expected result:** Flexibility for multi-monitor setups

______________________________________________________________________

### 4.3 Statistics & History

**Priority:** LOW | **Effort:** 3h | **Status:** ⏳ Pending

- [ ] Alarm counter (total, session)
- [ ] Timestamp history (last 10 alarms)
- [ ] Export to CSV/JSON
- [ ] Optional statistics display in the UI

**Expected result:** Usage analysis, pattern recognition

______________________________________________________________________

### 4.4 Extended Audio Options

**Priority:** LOW | **Effort:** 2h | **Status:** ⏳ Pending

- [ ] Volume slider in the UI
- [ ] Selectable custom sound files
- [ ] Test button for sounds
- [ ] Fade-in/fade-out effects

**Expected result:** Personalization

______________________________________________________________________

## Phase 5: Testing & CI/CD 🧪

### 5.1 Create Unit Tests

**Priority:** MEDIUM | **Effort:** 6h | **Status:** ⏳ Pending

- [ ] Test suite for the vision module
  - Template matching tests
  - Edge cases (no matches, too many matches)
- [ ] Test suite for the AlertManager
  - Alarm trigger logic
  - Cooldown functionality
- [ ] Test suite for configuration
  - Loading/saving settings
  - Validation
- [ ] Mock objects for UI tests
- [ ] Test coverage > 70%

**Expected result:** More stable releases, regression prevention

______________________________________________________________________

### 5.2 Integration Tests

**Priority:** LOW | **Effort:** 4h | **Status:** ⏳ Pending

- [ ] End-to-end test with mock screenshots
- [ ] Webhook integration tests
- [ ] Audio system tests
- [ ] Config persistence tests

**Expected result:** Full test coverage

______________________________________________________________________

### 5.3 Improve GitHub Actions

**Priority:** LOW | **Effort:** 2h | **Status:** ⏳ Pending

- [ ] Automatic tests on PR
- [ ] Code coverage reporting
- [ ] Automatic PyInstaller build
- [ ] Release automation

**Expected result:** Automated quality assurance

______________________________________________________________________

## Phase 6: Documentation 📚

### 6.1 Code Documentation

**Priority:** MEDIUM | **Effort:** 3h | **Status:** ⏳ Pending

- [ ] Docstrings for all public functions/classes
- [ ] Google/NumPy style docstrings
- [ ] Sphinx documentation setup (optional)
- [ ] Architecture Decision Records (ADRs)

**Expected result:** Better onboarding for contributors

______________________________________________________________________

### 6.2 User Documentation

**Priority:** LOW | **Effort:** 2h | **Status:** ⏳ Pending

- [ ] Extend the setup guide
- [ ] Troubleshooting section
- [ ] Create a FAQ
- [ ] Video tutorial (optional)
- [ ] Update screenshots

**Expected result:** Fewer support requests

______________________________________________________________________

## Prioritized Roadmap

### Sprint 1 (Weeks 1-2): Stability ⚡

1. Dependency synchronization
1. Error handling & validation
1. Screenshot optimization

**Goal:** Stable base version

______________________________________________________________________

### Sprint 2 (Weeks 3-4): Performance 🚀

1. Vision thread optimization
1. Eliminate magic numbers
1. Complete type hints

**Goal:** Optimized, maintainable code base

______________________________________________________________________

### Sprint 3 (Weeks 5-6): Features ✨

1. Runtime configuration
1. Improve logging
1. Statistics & history

**Goal:** Extended functionality

______________________________________________________________________

### Sprint 4 (Weeks 7-8): Testing 🧪

1. Create unit tests
1. Code documentation
1. Improve GitHub Actions

**Goal:** Professional code quality

______________________________________________________________________

### Backlog (Nice to Have) 💡

- Multi-monitor support
- Internationalization
- Integration tests
- Extended audio options
- User documentation

______________________________________________________________________

## Success Metrics

- ✅ 0 known critical bugs
- ✅ Test coverage > 70%
- ✅ CPU load < 5% when idle
- ✅ RAM usage < 150MB
- ✅ Startup time < 3 seconds
- ✅ 100% consistent dependencies
- ✅ Type hint coverage > 90%

______________________________________________________________________

## Notes & Decisions

### Dependency Decision

- Use `pyproject.toml` as the primary source
- Keep `requirements.txt` for backward compatibility
- Automatic sync via script

### Avoid Breaking Changes

- All changes must be backward compatible
- Existing config files must keep working
- Migration guide for larger changes

### Code Style

- Black formatter (already active)
- isort for imports
- pylint/flake8 for linting
- Pre-commit hooks (already active)

______________________________________________________________________

**Last updated:** November 17, 2025
**Responsible:** Development Team
**Status:** 📋 Planning
