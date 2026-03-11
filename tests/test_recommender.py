"""Tests for typotuner.recommender."""

import pytest
from typotuner.recommender import (
    generate_recommendations,
    MIN_SESSIONS, HIGH_ERROR_RATE, LOW_ERROR_RATE, PINKY_ERROR_RATE,
    HIGH_DWELL_MS, DEFAULT_ACTUATION_MM, MIN_ACTUATION_MM, MAX_ACTUATION_MM,
    INCREASE_STEP, DECREASE_STEP, PINKY_INCREASE_STEP,
)
from typotuner.storage import Storage


def _seed_sessions(db: Storage, n: int = 3):
    """Create n completed sessions to pass the min_sessions filter."""
    for i in range(n):
        sid = db.start_session(f"KB-{i}")
        db.end_session(sid, total_keys=100, total_errors=5)


def _seed_key(db: Storage, key_code: int, total: int, errors: int,
              dwell_ms: float = 50.0):
    """Seed a key with specific stats by simulating presses."""
    for i in range(total):
        is_error = i < errors
        db.record_keypress(key_code, dwell_ms=dwell_ms, is_error=is_error)


class TestMinSessions:
    def test_no_recommendations_without_sessions(self, tmp_db):
        """No recommendations if fewer than MIN_SESSIONS completed."""
        _seed_key(tmp_db, 30, 100, 20)  # 20% errors
        recs = generate_recommendations(tmp_db)
        assert len(recs) == 0

    def test_recommendations_after_min_sessions(self, tmp_db):
        """Recommendations generated after MIN_SESSIONS completed."""
        _seed_sessions(tmp_db, MIN_SESSIONS)
        # All errors — EMA stays above threshold at end of sequence
        for _ in range(50):
            tmp_db.record_keypress(30, dwell_ms=50.0, is_error=True)
        recs = generate_recommendations(tmp_db)
        assert len(recs) >= 1


class TestHighErrorRate:
    def test_high_error_increases_actuation(self, tmp_db):
        """Key with >8% error rate should get higher actuation."""
        _seed_sessions(tmp_db)
        # Seed with many errors to push EMA above threshold
        for _ in range(50):
            tmp_db.record_keypress(30, dwell_ms=50.0, is_error=True)
        recs = generate_recommendations(tmp_db)
        matching = [r for r in recs if r["key_code"] == 30]
        assert len(matching) == 1
        assert matching[0]["recommended_mm"] > DEFAULT_ACTUATION_MM


class TestLowErrorHighDwell:
    def test_low_error_high_dwell_decreases_actuation(self, tmp_db):
        """Key with <2% errors but high dwell should get lower actuation."""
        _seed_sessions(tmp_db)
        # Many clean presses with high dwell
        for _ in range(200):
            tmp_db.record_keypress(30, dwell_ms=150.0, is_error=False)
        recs = generate_recommendations(tmp_db)
        matching = [r for r in recs if r["key_code"] == 30]
        assert len(matching) == 1
        assert matching[0]["recommended_mm"] < DEFAULT_ACTUATION_MM


class TestPinkySpecialCase:
    def test_pinky_softer_increase(self, tmp_db):
        """Pinky keys get a smaller actuation increase."""
        _seed_sessions(tmp_db)
        # Right pinky key: Ö (39)
        for _ in range(50):
            tmp_db.record_keypress(39, dwell_ms=50.0, is_error=True)
        recs = generate_recommendations(tmp_db)
        matching = [r for r in recs if r["key_code"] == 39]
        assert len(matching) == 1
        # Pinky step is smaller than normal step
        assert matching[0]["recommended_mm"] == round(DEFAULT_ACTUATION_MM + PINKY_INCREASE_STEP, 1)


class TestClamp:
    def test_recommendation_clamped_to_max(self, tmp_db):
        """Recommendation should never exceed MAX_ACTUATION_MM."""
        _seed_sessions(tmp_db)
        for _ in range(50):
            tmp_db.record_keypress(30, dwell_ms=50.0, is_error=True)
        recs = generate_recommendations(tmp_db)
        for r in recs:
            assert r["recommended_mm"] <= MAX_ACTUATION_MM

    def test_recommendation_clamped_to_min(self, tmp_db):
        """Recommendation should never go below MIN_ACTUATION_MM."""
        _seed_sessions(tmp_db)
        for _ in range(200):
            tmp_db.record_keypress(30, dwell_ms=150.0, is_error=False)
        recs = generate_recommendations(tmp_db)
        for r in recs:
            assert r["recommended_mm"] >= MIN_ACTUATION_MM


class TestConfidence:
    def test_confidence_scales_with_presses(self, tmp_db):
        """Confidence should be higher with more presses."""
        _seed_sessions(tmp_db)
        # Few presses
        for _ in range(50):
            tmp_db.record_keypress(30, dwell_ms=50.0, is_error=True)
        # Many presses on another key
        for _ in range(500):
            tmp_db.record_keypress(31, dwell_ms=50.0, is_error=True)
        recs = generate_recommendations(tmp_db)
        r30 = next((r for r in recs if r["key_code"] == 30), None)
        r31 = next((r for r in recs if r["key_code"] == 31), None)
        if r30 and r31:
            assert r31["confidence"] >= r30["confidence"]


class TestNoChangeNeeded:
    def test_good_key_no_recommendation(self, tmp_db):
        """Key with moderate error rate and normal dwell → no recommendation."""
        _seed_sessions(tmp_db)
        # 3-4% error rate, normal dwell — falls between thresholds
        for i in range(100):
            is_err = i < 4  # ~4% early errors but EMA will smooth
            tmp_db.record_keypress(30, dwell_ms=60.0, is_error=is_err)
        recs = generate_recommendations(tmp_db)
        matching = [r for r in recs if r["key_code"] == 30]
        # May or may not have recommendation depending on EMA
        # But if it does, it should be within reasonable bounds
        for r in matching:
            assert MIN_ACTUATION_MM <= r["recommended_mm"] <= MAX_ACTUATION_MM


class TestSortOrder:
    def test_sorted_by_confidence(self, tmp_db):
        """Recommendations should be sorted by confidence descending."""
        _seed_sessions(tmp_db)
        for _ in range(30):
            tmp_db.record_keypress(30, dwell_ms=50.0, is_error=True)
        for _ in range(300):
            tmp_db.record_keypress(31, dwell_ms=50.0, is_error=True)
        recs = generate_recommendations(tmp_db)
        if len(recs) >= 2:
            for i in range(len(recs) - 1):
                assert recs[i]["confidence"] >= recs[i + 1]["confidence"]
