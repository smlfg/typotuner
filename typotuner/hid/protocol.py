"""SteelSeries Apex Pro TKL 2023 protocol — encode/decode actuation data.

WARNING: Protocol details derived from reverse engineering.
The feature report on Interface 1 (Vendor Usage Page 0xFFC0) contains
per-key actuation point data embedded in a 644-byte report.

Protocol structure (to be refined after RE):
- Feature Report ID: 0x00 (or device-specific)
- Actuation data region: bytes at known offsets within the 644-byte report
- Each key has an actuation value encoded as a single byte:
    byte_value = round((actuation_mm - 0.1) / 0.1)
    → 0x00 = 0.1mm, 0x01 = 0.2mm, ..., 0x27 = 4.0mm (39 steps, 40 values)
- Default actuation: 2.0mm → byte value 0x13 (19)

TODO: Fill in actual offsets after Step 0 (Feature Report diff with Fn+O/I).
"""

from __future__ import annotations

# Actuation range
MIN_MM = 0.1
MAX_MM = 4.0
STEP_MM = 0.1
DEFAULT_MM = 2.0

# Byte encoding
MIN_BYTE = 0x00   # 0.1mm
MAX_BYTE = 0x27   # 4.0mm (39)
DEFAULT_BYTE = 0x13  # 2.0mm (19)

# Feature report layout (placeholder offsets — to be filled after RE)
# These will be populated after analyzing Fn+O/I diffs
REPORT_ID = 0x00
REPORT_SIZE = 644

# Offset where actuation data starts within the feature report
# and the layout of per-key actuation bytes.
# Format: ACTUATION_OFFSET + key_position → actuation byte
#
# TODO(RE): Determine these from Feature Report diff:
#   1. Read report at default settings
#   2. Change actuation via Fn+O/I
#   3. Read again → diff reveals actuation byte region
ACTUATION_OFFSET: int | None = None  # To be determined
ACTUATION_LENGTH: int | None = None  # Number of key slots

# Preset actuation values for Fn+O/I presets (if the keyboard has them)
PRESET_VALUES_MM = {
    1: 0.5,   # Preset 1 (fast)
    2: 1.0,   # Preset 2
    3: 2.0,   # Preset 3 (default)
    4: 3.5,   # Preset 4 (heavy)
}


class ProtocolError(Exception):
    """Raised when protocol encode/decode fails."""


def mm_to_byte(mm: float) -> int:
    """Convert actuation distance in mm to protocol byte value.

    Args:
        mm: Actuation distance (0.1 — 4.0mm)

    Returns:
        Byte value (0x00 — 0x27)

    Raises:
        ProtocolError: If mm is out of range
    """
    if not (MIN_MM - 0.001 <= mm <= MAX_MM + 0.001):
        raise ProtocolError(f"Actuation {mm}mm out of range [{MIN_MM}, {MAX_MM}]")
    byte_val = round((mm - MIN_MM) / STEP_MM)
    return max(MIN_BYTE, min(MAX_BYTE, byte_val))


def byte_to_mm(byte_val: int) -> float:
    """Convert protocol byte value to actuation distance in mm.

    Args:
        byte_val: Raw byte (0x00 — 0x27)

    Returns:
        Actuation distance in mm (0.1 — 4.0)

    Raises:
        ProtocolError: If byte value is out of range
    """
    if not (MIN_BYTE <= byte_val <= MAX_BYTE):
        raise ProtocolError(f"Byte value 0x{byte_val:02X} out of range [0x{MIN_BYTE:02X}, 0x{MAX_BYTE:02X}]")
    return round(MIN_MM + byte_val * STEP_MM, 1)


def decode_actuation_map(report: bytes) -> dict[int, float] | None:
    """Extract per-key actuation values from a feature report.

    Args:
        report: Raw 644-byte feature report

    Returns:
        Dict mapping key_position → actuation_mm, or None if offsets unknown

    Raises:
        ProtocolError: If report is too short or data is invalid
    """
    if len(report) < REPORT_SIZE:
        raise ProtocolError(f"Report too short: {len(report)} < {REPORT_SIZE}")

    if ACTUATION_OFFSET is None or ACTUATION_LENGTH is None:
        return None

    actuation = {}
    for i in range(ACTUATION_LENGTH):
        offset = ACTUATION_OFFSET + i
        if offset >= len(report):
            break
        byte_val = report[offset]
        if MIN_BYTE <= byte_val <= MAX_BYTE:
            actuation[i] = byte_to_mm(byte_val)
    return actuation


def encode_actuation_map(
    report: bytes,
    changes: dict[int, float],
) -> bytes:
    """Apply per-key actuation changes to a feature report (read-modify-write).

    Args:
        report: Original 644-byte feature report (will NOT be modified)
        changes: Dict mapping key_position → new actuation_mm

    Returns:
        Modified report with updated actuation bytes

    Raises:
        ProtocolError: If offsets unknown or values out of range
    """
    if ACTUATION_OFFSET is None or ACTUATION_LENGTH is None:
        raise ProtocolError(
            "Actuation offsets not yet determined. "
            "Run reverse engineering (Step 0) first."
        )

    modified = bytearray(report)
    for key_pos, mm in changes.items():
        if not (0 <= key_pos < ACTUATION_LENGTH):
            raise ProtocolError(f"Key position {key_pos} out of range [0, {ACTUATION_LENGTH})")
        offset = ACTUATION_OFFSET + key_pos
        modified[offset] = mm_to_byte(mm)
    return bytes(modified)


def diff_reports(report_a: bytes, report_b: bytes) -> list[tuple[int, int, int]]:
    """Find all byte differences between two reports.

    Useful for reverse engineering: read report, change setting, read again, diff.

    Args:
        report_a: First report (e.g., before Fn+O/I)
        report_b: Second report (e.g., after Fn+O/I)

    Returns:
        List of (offset, byte_a, byte_b) for each differing byte
    """
    min_len = min(len(report_a), len(report_b))
    diffs = []
    for i in range(min_len):
        if report_a[i] != report_b[i]:
            diffs.append((i, report_a[i], report_b[i]))
    return diffs


def format_diff(diffs: list[tuple[int, int, int]]) -> str:
    """Format report diffs for human review.

    Args:
        diffs: Output from diff_reports()

    Returns:
        Multi-line string showing offsets and values
    """
    if not diffs:
        return "No differences found."

    lines = [f"Found {len(diffs)} differing bytes:\n"]
    lines.append(f"{'Offset':>8}  {'Hex':>6}  {'Before':>6} → {'After':>6}  {'As mm':>10}")
    lines.append("-" * 50)
    for offset, a, b in diffs:
        mm_a = f"{byte_to_mm(a):.1f}mm" if MIN_BYTE <= a <= MAX_BYTE else "?"
        mm_b = f"{byte_to_mm(b):.1f}mm" if MIN_BYTE <= b <= MAX_BYTE else "?"
        lines.append(
            f"  0x{offset:04X}  ({offset:>4d})  0x{a:02X} ({a:>3d}) → 0x{b:02X} ({b:>3d})  {mm_a} → {mm_b}"
        )
    return "\n".join(lines)
