"""Actuation recommendation engine for SteelSeries Apex Pro TKL.

Analyzes per-key error rates and timing to suggest actuation point
adjustments (0.1mm — 4.0mm range, 40 steps).

Rules:
- error_rate > 8%  → INCREASE actuation (too sensitive, accidental presses)
- error_rate < 2% + high dwell → DECREASE actuation (key too hard to press)
- Pinky keys + error_rate > 5% → softer increase (weaker finger)
- Confidence = min(1.0, total_presses / 500)
- Filter: min_sessions >= 3 before generating recommendations
"""

from __future__ import annotations

from .storage import Storage
from . import qwertz

# Actuation range for SteelSeries Apex Pro TKL
MIN_ACTUATION_MM = 0.1
MAX_ACTUATION_MM = 4.0
DEFAULT_ACTUATION_MM = 2.0

# Thresholds
HIGH_ERROR_RATE = 0.08      # 8% — too many accidental presses
LOW_ERROR_RATE = 0.02       # 2% — key is fine
PINKY_ERROR_RATE = 0.05     # 5% — softer threshold for weak fingers
HIGH_DWELL_MS = 120.0       # ms — key might be too hard to press
MIN_PRESSES_CONFIDENCE = 500  # presses for full confidence
MIN_SESSIONS = 3            # minimum completed sessions before recommending

# Step sizes (mm)
INCREASE_STEP = 0.3         # make less sensitive
DECREASE_STEP = 0.2         # make more sensitive
PINKY_INCREASE_STEP = 0.2   # gentler for pinky

PINKY_FINGERS = {"left_pinky", "right_pinky"}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def generate_recommendations(storage: Storage) -> list[dict]:
    """Generate actuation recommendations for all tracked keys.

    Returns list of dicts with keys:
      key_code, key_name, current_mm, recommended_mm, reason, confidence
    """
    # Check minimum sessions
    if storage.session_count() < MIN_SESSIONS:
        return []

    all_stats = storage.get_key_stats()
    if not all_stats:
        return []

    recommendations = []

    for stat in all_stats:
        key_code = stat["key_code"]
        key_name = stat["key_name"]
        finger = stat["finger"]
        error_ema = stat["error_rate_ema"]
        dwell_ema = stat["dwell_ema"]
        total_presses = stat["total_presses"]

        # Skip keys with too few presses
        if total_presses < 20:
            continue

        confidence = min(1.0, total_presses / MIN_PRESSES_CONFIDENCE)
        current_mm = DEFAULT_ACTUATION_MM
        recommended_mm = current_mm
        reason = ""

        is_pinky = finger in PINKY_FINGERS

        if is_pinky and error_ema > PINKY_ERROR_RATE:
            # Pinky: softer increase
            recommended_mm = current_mm + PINKY_INCREASE_STEP
            reason = (
                f"Pinky-Taste mit {error_ema:.1%} Fehlerrate — "
                f"Actuation leicht erhoehen (schwacher Finger)"
            )
        elif error_ema > HIGH_ERROR_RATE:
            # High error rate: increase actuation (less sensitive)
            recommended_mm = current_mm + INCREASE_STEP
            reason = (
                f"{error_ema:.1%} Fehlerrate — "
                f"Actuation erhoehen (zu empfindlich, versehentliche Druecke)"
            )
        elif error_ema < LOW_ERROR_RATE and dwell_ema > HIGH_DWELL_MS:
            # Low errors but slow: decrease actuation (more sensitive)
            recommended_mm = current_mm - DECREASE_STEP
            reason = (
                f"Nur {error_ema:.1%} Fehler aber {dwell_ema:.0f}ms Haltezeit — "
                f"Actuation senken (Taste zu schwer)"
            )
        else:
            # No change needed
            continue

        recommended_mm = _clamp(recommended_mm, MIN_ACTUATION_MM, MAX_ACTUATION_MM)

        # Skip if recommendation is same as current
        if abs(recommended_mm - current_mm) < 0.05:
            continue

        recommendations.append({
            "key_code": key_code,
            "key_name": key_name,
            "current_mm": current_mm,
            "recommended_mm": round(recommended_mm, 1),
            "reason": reason,
            "confidence": round(confidence, 3),
        })

    # Sort by confidence descending
    recommendations.sort(key=lambda r: r["confidence"], reverse=True)
    return recommendations
