"""Typing analyzer — typo detection and timing metrics.

Processes raw evdev key events, detects errors via backspace heuristic,
classifies error types, and updates storage with EMA-smoothed stats.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import qwertz
from .storage import Storage


@dataclass
class KeyEvent:
    """Raw key event from evdev."""
    key_code: int
    timestamp_ns: int  # monotonic nanoseconds
    is_down: bool  # True = key_down, False = key_up


# evdev key code for backspace
KEY_BACKSPACE = 14

# Max time between last key and backspace to count as correction (ms)
BACKSPACE_WINDOW_MS = 500

# Max time between same key presses to count as double-press (ms)
DOUBLE_PRESS_WINDOW_MS = 80

# Minimum dwell time to be considered intentional (ms) — filter bounces
MIN_DWELL_MS = 5.0


@dataclass
class AnalyzerState:
    """Tracks state for typo detection."""
    # Last non-backspace key_down event
    last_key_code: int | None = None
    last_key_down_ns: int | None = None
    last_key_up_ns: int | None = None
    # Second-to-last key (for double-press detection)
    prev_key_code: int | None = None
    # Counters for current session
    total_keys: int = 0
    total_errors: int = 0


class Analyzer:
    """Stateful typing analyzer.

    Feed events via process_event(). The analyzer detects typos
    (backspace within 500ms of last keypress), classifies them,
    and writes stats to storage.
    """

    def __init__(self, storage: Storage):
        self._storage = storage
        self._state = AnalyzerState()

    @property
    def state(self) -> AnalyzerState:
        return self._state

    def process_event(self, event: KeyEvent) -> str | None:
        """Process a single key event.

        Returns error_type string if a typo was detected, else None.
        """
        s = self._state

        if event.is_down:
            return self._handle_key_down(event)
        else:
            return self._handle_key_up(event)

    def _handle_key_down(self, event: KeyEvent) -> str | None:
        s = self._state

        if event.key_code == KEY_BACKSPACE:
            return self._handle_backspace(event)

        # Calculate flight time (inter-key interval) from last key_down
        flight_ms = 0.0
        if s.last_key_down_ns is not None:
            flight_ms = (event.timestamp_ns - s.last_key_down_ns) / 1_000_000

        # Update state
        s.prev_key_code = s.last_key_code
        s.last_key_code = event.key_code
        s.last_key_down_ns = event.timestamp_ns
        s.last_key_up_ns = None  # reset, will be set on key_up
        s.total_keys += 1

        # Record keypress (dwell will be updated on key_up)
        self._storage.record_keypress(
            event.key_code,
            dwell_ms=0.0,  # placeholder, updated on key_up
            flight_ms=flight_ms,
            is_error=False,
        )

        return None

    def _handle_key_up(self, event: KeyEvent) -> None:
        """Track key release for dwell time calculation."""
        s = self._state
        if event.key_code == s.last_key_code and s.last_key_down_ns is not None:
            s.last_key_up_ns = event.timestamp_ns
        return None

    def _handle_backspace(self, event: KeyEvent) -> str | None:
        """Detect and classify typo when backspace is pressed."""
        s = self._state

        if s.last_key_code is None or s.last_key_down_ns is None:
            return None

        elapsed_ms = (event.timestamp_ns - s.last_key_down_ns) / 1_000_000

        if elapsed_ms > BACKSPACE_WINDOW_MS:
            return None  # Too long ago, probably intentional deletion

        # This is a correction — classify the error
        error_key = s.last_key_code
        error_type = self._classify_error(error_key, s.prev_key_code, elapsed_ms)

        # Mark the previous key as an error in storage
        self._storage.record_keypress(error_key, is_error=True)
        s.total_errors += 1

        # Record typo event
        correction_ms = int(elapsed_ms)
        intended_key = s.prev_key_code  # best guess
        self._storage.record_typo(
            error_key=error_key,
            intended_key=intended_key,
            correction_ms=correction_ms,
            error_type=error_type,
        )

        return error_type

    def _classify_error(self, error_key: int, prev_key: int | None,
                        elapsed_ms: float) -> str:
        """Classify a typo error.

        Types:
        - 'adjacent': wrong key is a physical neighbor of the likely intended key
        - 'double': same key pressed twice rapidly (bounce or stutter)
        - 'timing': very short interval suggests accidental press
        - 'unknown': doesn't match other patterns
        """
        # Double press: same key as previous
        if prev_key is not None and error_key == prev_key:
            return "double"

        # Adjacent: error key is neighbor of previous key
        if prev_key is not None and qwertz.is_neighbor(error_key, prev_key):
            return "adjacent"

        # Timing: very fast press suggests accidental
        if elapsed_ms < DOUBLE_PRESS_WINDOW_MS:
            return "timing"

        return "unknown"

    def get_dwell_ms(self) -> float:
        """Calculate dwell time of the last key (if we have both down and up)."""
        s = self._state
        if s.last_key_down_ns is not None and s.last_key_up_ns is not None:
            return (s.last_key_up_ns - s.last_key_down_ns) / 1_000_000
        return 0.0
