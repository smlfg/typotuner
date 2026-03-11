"""Tests for typotuner.storage."""

from typotuner.storage import Storage, TYPO_RING_BUFFER_SIZE


class TestKeyStats:
    def test_record_first_keypress(self, tmp_db):
        """First press of a key creates a new row."""
        tmp_db.record_keypress(30, dwell_ms=50.0, flight_ms=100.0)  # A key
        stats = tmp_db.get_key_stats(30)
        assert len(stats) == 1
        assert stats[0]["total_presses"] == 1
        assert stats[0]["key_name"] == "A"
        assert stats[0]["finger"] == "left_pinky"

    def test_record_multiple_presses(self, tmp_db):
        """Multiple presses increment counter and update EMA."""
        for _ in range(10):
            tmp_db.record_keypress(30, dwell_ms=50.0)
        stats = tmp_db.get_key_stats(30)
        assert stats[0]["total_presses"] == 10
        assert stats[0]["total_errors"] == 0

    def test_record_error(self, tmp_db):
        """Error flag updates error count and EMA."""
        tmp_db.record_keypress(30, is_error=True)
        stats = tmp_db.get_key_stats(30)
        assert stats[0]["total_errors"] == 1
        assert stats[0]["error_rate_ema"] == 1.0  # first press, error

    def test_ema_converges(self, tmp_db):
        """EMA error rate should decrease with successful presses after an error."""
        tmp_db.record_keypress(30, is_error=True)
        for _ in range(20):
            tmp_db.record_keypress(30, is_error=False)
        stats = tmp_db.get_key_stats(30)
        assert stats[0]["error_rate_ema"] < 0.5  # converging down

    def test_get_all_key_stats(self, tmp_db):
        """get_key_stats without args returns all keys."""
        tmp_db.record_keypress(30)  # A
        tmp_db.record_keypress(31)  # S
        stats = tmp_db.get_key_stats()
        assert len(stats) == 2

    def test_daily_reset(self, tmp_db):
        """Daily counters should track correctly within same day."""
        tmp_db.record_keypress(30)
        tmp_db.record_keypress(30)
        stats = tmp_db.get_key_stats(30)
        assert stats[0]["daily_presses"] == 2

    def test_unknown_key(self, tmp_db):
        """Unknown key codes get a fallback name."""
        tmp_db.record_keypress(999)
        stats = tmp_db.get_key_stats(999)
        assert stats[0]["key_name"] == "KEY_999"
        assert stats[0]["finger"] is None


class TestFingerStats:
    def test_aggregate_by_finger(self, tmp_db):
        """Finger stats aggregate across keys."""
        # A (30) and Q (16) are both left_pinky
        tmp_db.record_keypress(30)
        tmp_db.record_keypress(16)
        fingers = tmp_db.get_finger_stats()
        assert "left_pinky" in fingers
        assert fingers["left_pinky"]["total_presses"] == 2


class TestTypoEvents:
    def test_record_typo(self, tmp_db):
        """Recording a typo creates an event."""
        tmp_db.record_typo(31, intended_key=30, correction_ms=200, error_type="adjacent")
        events = tmp_db.get_typo_events()
        assert len(events) == 1
        assert events[0]["error_type"] == "adjacent"

    def test_ring_buffer_trim(self, tmp_db):
        """Ring buffer should not exceed TYPO_RING_BUFFER_SIZE."""
        # Insert more than buffer size (use smaller number for test speed)
        for i in range(50):
            tmp_db.record_typo(31, None, 100, "unknown")
        events = tmp_db.get_typo_events(limit=10000)
        assert len(events) <= TYPO_RING_BUFFER_SIZE

    def test_typo_summary(self, tmp_db):
        """Typo summary groups by type."""
        tmp_db.record_typo(31, None, 100, "adjacent")
        tmp_db.record_typo(32, None, 200, "timing")
        tmp_db.record_typo(33, None, 150, "adjacent")
        summary = tmp_db.get_typo_summary()
        assert summary["adjacent"] == 2
        assert summary["timing"] == 1


class TestSessions:
    def test_start_end_session(self, tmp_db):
        """Session lifecycle works."""
        sid = tmp_db.start_session("Test Keyboard")
        assert sid is not None
        tmp_db.end_session(sid, total_keys=100, total_errors=5)
        sessions = tmp_db.get_sessions()
        assert len(sessions) == 1
        assert sessions[0]["total_keys"] == 100

    def test_session_count(self, tmp_db):
        """session_count only counts completed sessions."""
        sid1 = tmp_db.start_session("KB1")
        tmp_db.end_session(sid1, 50, 2)
        sid2 = tmp_db.start_session("KB2")  # not ended
        assert tmp_db.session_count() == 1


class TestReset:
    def test_reset_clears_all(self, tmp_db):
        """Reset removes all data."""
        tmp_db.record_keypress(30)
        tmp_db.record_typo(31, None, 100, "unknown")
        tmp_db.start_session("KB")
        tmp_db.reset()
        assert len(tmp_db.get_key_stats()) == 0
        assert len(tmp_db.get_typo_events()) == 0
        assert len(tmp_db.get_sessions()) == 0
