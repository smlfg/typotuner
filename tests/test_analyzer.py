"""Tests for typotuner.analyzer."""

import pytest
from typotuner.analyzer import (
    Analyzer, KeyEvent, KEY_BACKSPACE,
    BACKSPACE_WINDOW_MS, DOUBLE_PRESS_WINDOW_MS,
)
from typotuner.storage import Storage


def _ns(ms: float) -> int:
    """Convert ms to nanoseconds."""
    return int(ms * 1_000_000)


def _down(key_code: int, time_ms: float) -> KeyEvent:
    return KeyEvent(key_code=key_code, timestamp_ns=_ns(time_ms), is_down=True)


def _up(key_code: int, time_ms: float) -> KeyEvent:
    return KeyEvent(key_code=key_code, timestamp_ns=_ns(time_ms), is_down=False)


class TestTypoDetection:
    def test_no_typo_normal_typing(self, tmp_db):
        """Normal sequential keypresses should not trigger typo."""
        ana = Analyzer(tmp_db)
        assert ana.process_event(_down(30, 0)) is None      # A down
        assert ana.process_event(_up(30, 50)) is None        # A up
        assert ana.process_event(_down(31, 100)) is None     # S down

    def test_backspace_within_window_is_typo(self, tmp_db):
        """Backspace within 500ms of last key = typo detected."""
        ana = Analyzer(tmp_db)
        ana.process_event(_down(30, 0))       # A
        ana.process_event(_down(31, 100))      # S (typo)
        result = ana.process_event(_down(KEY_BACKSPACE, 200))  # BS within 100ms
        assert result is not None

    def test_backspace_outside_window_no_typo(self, tmp_db):
        """Backspace after 500ms should not be flagged as typo."""
        ana = Analyzer(tmp_db)
        ana.process_event(_down(30, 0))
        ana.process_event(_down(31, 100))
        result = ana.process_event(_down(KEY_BACKSPACE, 700))  # 600ms after S
        assert result is None

    def test_adjacent_error_classification(self, tmp_db):
        """Error key that is neighbor of prev key -> 'adjacent'."""
        ana = Analyzer(tmp_db)
        # S (31) and D (32) are neighbors
        ana.process_event(_down(31, 0))        # S
        ana.process_event(_down(32, 100))      # D (neighbor of S)
        result = ana.process_event(_down(KEY_BACKSPACE, 200))
        assert result == "adjacent"

    def test_double_press_classification(self, tmp_db):
        """Same key pressed twice -> 'double'."""
        ana = Analyzer(tmp_db)
        ana.process_event(_down(30, 0))        # A
        ana.process_event(_down(30, 50))       # A again
        result = ana.process_event(_down(KEY_BACKSPACE, 100))
        assert result == "double"

    def test_timing_error_classification(self, tmp_db):
        """Very fast press of non-adjacent, non-double key -> 'timing'."""
        ana = Analyzer(tmp_db)
        # Q (16) and M (50) are not neighbors
        ana.process_event(_down(16, 0))        # Q
        ana.process_event(_down(50, 30))       # M (very fast, 30ms, non-adjacent)
        result = ana.process_event(_down(KEY_BACKSPACE, 60))
        assert result == "timing"

    def test_unknown_error_classification(self, tmp_db):
        """Non-adjacent, non-double, slow enough -> 'unknown'."""
        ana = Analyzer(tmp_db)
        # Q (16) and M (50) are not neighbors
        ana.process_event(_down(16, 0))        # Q
        ana.process_event(_down(50, 200))      # M (not adjacent, not fast)
        result = ana.process_event(_down(KEY_BACKSPACE, 300))
        assert result == "unknown"

    def test_backspace_without_previous_key(self, tmp_db):
        """Backspace as first event should not crash."""
        ana = Analyzer(tmp_db)
        result = ana.process_event(_down(KEY_BACKSPACE, 100))
        assert result is None


class TestCounters:
    def test_total_keys_increment(self, tmp_db):
        """total_keys should count non-backspace key_downs."""
        ana = Analyzer(tmp_db)
        ana.process_event(_down(30, 0))
        ana.process_event(_down(31, 100))
        ana.process_event(_down(32, 200))
        assert ana.state.total_keys == 3

    def test_total_errors_increment(self, tmp_db):
        """total_errors should count detected typos."""
        ana = Analyzer(tmp_db)
        ana.process_event(_down(30, 0))
        ana.process_event(_down(31, 100))
        ana.process_event(_down(KEY_BACKSPACE, 200))
        assert ana.state.total_errors == 1

    def test_backspace_not_counted_as_key(self, tmp_db):
        """Backspace should not increment total_keys."""
        ana = Analyzer(tmp_db)
        ana.process_event(_down(30, 0))
        ana.process_event(_down(KEY_BACKSPACE, 100))
        assert ana.state.total_keys == 1


class TestDwellTime:
    def test_dwell_time_calculation(self, tmp_db):
        """Dwell = key_up_time - key_down_time."""
        ana = Analyzer(tmp_db)
        ana.process_event(_down(30, 0))
        ana.process_event(_up(30, 80))
        assert abs(ana.get_dwell_ms() - 80.0) < 0.01

    def test_dwell_no_key_up(self, tmp_db):
        """Without key_up, dwell should be 0."""
        ana = Analyzer(tmp_db)
        ana.process_event(_down(30, 0))
        assert ana.get_dwell_ms() == 0.0


class TestFlightTime:
    def test_flight_time_stored(self, tmp_db):
        """Flight time between keypresses should be stored."""
        ana = Analyzer(tmp_db)
        ana.process_event(_down(30, 0))      # A at 0ms
        ana.process_event(_down(31, 150))    # S at 150ms
        stats = tmp_db.get_key_stats(31)
        assert len(stats) == 1
        assert abs(stats[0]["avg_flight_ms"] - 150.0) < 1.0

    def test_first_key_zero_flight(self, tmp_db):
        """First keypress should have 0 flight time."""
        ana = Analyzer(tmp_db)
        ana.process_event(_down(30, 0))
        stats = tmp_db.get_key_stats(30)
        assert stats[0]["avg_flight_ms"] == 0.0


class TestStorageIntegration:
    def test_typo_recorded_in_storage(self, tmp_db):
        """Typo events should appear in storage."""
        ana = Analyzer(tmp_db)
        ana.process_event(_down(30, 0))
        ana.process_event(_down(31, 100))
        ana.process_event(_down(KEY_BACKSPACE, 200))
        events = tmp_db.get_typo_events()
        assert len(events) == 1
        assert events[0]["error_key_code"] == 31

    def test_error_flag_in_key_stats(self, tmp_db):
        """Error should be reflected in key_stats error_rate_ema."""
        ana = Analyzer(tmp_db)
        ana.process_event(_down(30, 0))
        ana.process_event(_down(31, 100))
        ana.process_event(_down(KEY_BACKSPACE, 200))
        stats = tmp_db.get_key_stats(31)
        assert stats[0]["total_errors"] >= 1
