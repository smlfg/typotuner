"""Keycode mapping: evdev key codes <-> SteelSeries key positions.

Maps between Linux evdev key codes (used by TypoTuner's analyzer/qwertz module)
and the key position indices used in the SteelSeries HID feature report.

The SteelSeries position index corresponds to the position of each key's
actuation byte within the feature report's actuation data region.

TODO(RE): The SS_POSITION map below uses USB HID Usage Page 0x07 scancodes
as a reasonable starting assumption. Must be verified against actual
feature report captures. Some keys may use non-standard positions.
"""

from __future__ import annotations

from .. import qwertz

# ---------------------------------------------------------------------------
# EVDEV_TO_SS: evdev key_code -> SteelSeries key position in actuation map
# ---------------------------------------------------------------------------
# Based on USB HID Usage Page 0x07 (Keyboard/Keypad) scancodes.
# The SteelSeries firmware likely uses these internally.
# Assumption: position index in the actuation region = USB HID scancode.
#
# TODO(RE): Verify each mapping against captured feature report diffs.
#           Change a single key's actuation in SteelSeries GG, capture
#           the report, identify which position byte changed.
# ---------------------------------------------------------------------------

# USB HID Usage IDs for keyboard keys (Usage Page 0x07)
# Reference: USB HID Usage Tables, Section 10 "Keyboard/Keypad Page"
EVDEV_TO_SS: dict[int, int] = {
    # --- Number row ---
    41: 0x35,  # ^ (Grave/Tilde) → HID 0x35
    2:  0x1E,  # 1 → HID 0x1E
    3:  0x1F,  # 2 → HID 0x1F
    4:  0x20,  # 3 → HID 0x20
    5:  0x21,  # 4 → HID 0x21
    6:  0x22,  # 5 → HID 0x22
    7:  0x23,  # 6 → HID 0x23
    8:  0x24,  # 7 → HID 0x24
    9:  0x25,  # 8 → HID 0x25
    10: 0x26,  # 9 → HID 0x26
    11: 0x27,  # 0 → HID 0x27
    12: 0x2D,  # ß (Minus) → HID 0x2D
    13: 0x2E,  # ´ (Equal) → HID 0x2E
    14: 0x2A,  # Backspace → HID 0x2A

    # --- Top letter row ---
    15: 0x2B,  # Tab → HID 0x2B
    16: 0x14,  # Q → HID 0x14
    17: 0x1A,  # W → HID 0x1A
    18: 0x08,  # E → HID 0x08
    19: 0x15,  # R → HID 0x15
    20: 0x17,  # T → HID 0x17
    21: 0x1C,  # Z (evdev KEY_Y, QWERTZ: Z) → HID 0x1C (Y in USB)
    22: 0x18,  # U → HID 0x18
    23: 0x0C,  # I → HID 0x0C
    24: 0x12,  # O → HID 0x12
    25: 0x13,  # P → HID 0x13
    26: 0x2F,  # Ü (Left Bracket) → HID 0x2F
    27: 0x30,  # + (Right Bracket) → HID 0x30

    # --- Home row ---
    30: 0x04,  # A → HID 0x04
    31: 0x16,  # S → HID 0x16
    32: 0x07,  # D → HID 0x07
    33: 0x09,  # F → HID 0x09
    34: 0x0A,  # G → HID 0x0A
    35: 0x0B,  # H → HID 0x0B
    36: 0x0D,  # J → HID 0x0D
    37: 0x0E,  # K → HID 0x0E
    38: 0x0F,  # L → HID 0x0F
    39: 0x33,  # Ö (Semicolon) → HID 0x33
    40: 0x34,  # Ä (Apostrophe) → HID 0x34
    43: 0x32,  # # (Backslash, ISO) → HID 0x32
    28: 0x28,  # Enter → HID 0x28

    # --- Bottom row ---
    86: 0x64,  # < (ISO extra key) → HID 0x64
    44: 0x1D,  # Y (evdev KEY_Z, QWERTZ: Y) → HID 0x1D (Z in USB)
    45: 0x1B,  # X → HID 0x1B
    46: 0x06,  # C → HID 0x06
    47: 0x19,  # V → HID 0x19
    48: 0x05,  # B → HID 0x05
    49: 0x11,  # N → HID 0x11
    50: 0x10,  # M → HID 0x10
    51: 0x36,  # , → HID 0x36
    52: 0x37,  # . → HID 0x37
    53: 0x38,  # - (Slash) → HID 0x38

    # --- Modifiers & special ---
    57: 0x2C,  # Space → HID 0x2C
    1:  0x29,  # Escape → HID 0x29
}

# Reverse map: SS position → evdev key code
SS_TO_EVDEV: dict[int, int] = {v: k for k, v in EVDEV_TO_SS.items()}


def evdev_to_ss(key_code: int) -> int | None:
    """Convert evdev key code to SteelSeries key position.

    Returns None if the key is not mapped.
    """
    return EVDEV_TO_SS.get(key_code)


def ss_to_evdev(ss_pos: int) -> int | None:
    """Convert SteelSeries key position to evdev key code.

    Returns None if the position is not mapped.
    """
    return SS_TO_EVDEV.get(ss_pos)


def evdev_to_label(key_code: int) -> str:
    """Get QWERTZ label for an evdev key code."""
    return qwertz.get_label(key_code) or f"KEY_{key_code}"


def validate_keymap() -> list[str]:
    """Check that all keys in FINGER_MAP have a SS mapping.

    Returns list of warning messages for unmapped keys.
    """
    warnings = []
    for key_code in qwertz.FINGER_MAP:
        if key_code not in EVDEV_TO_SS:
            label = qwertz.get_label(key_code) or f"KEY_{key_code}"
            warnings.append(f"Key {label} (evdev {key_code}) has no SteelSeries mapping")
    return warnings
