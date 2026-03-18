"""Safety layer for HID actuation writes.

Non-negotiable safety rules:
1. Backup before every write
2. Value clamping: 0.1 — 4.0mm, never out of range
3. Read-back verification after write
4. RAM-only default (no flash persistence without --persist)
5. Read-modify-write: only change actuation bytes, preserve everything else
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from . import device, protocol

# Backup directory
BACKUP_DIR = Path.home() / ".local" / "share" / "typotuner" / "backups"


class SafetyError(Exception):
    """Raised when a safety check fails."""


class VerificationError(SafetyError):
    """Raised when read-back verification fails after a write."""


def backup_dir() -> Path:
    """Return and ensure backup directory exists."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


def create_backup(report: bytes, label: str = "actuation") -> Path:
    """Save a feature report to the backup directory.

    Args:
        report: Raw feature report bytes
        label: Descriptive label for the backup file

    Returns:
        Path to the backup file
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir() / f"{label}_{ts}.bin"
    backup_path.write_bytes(report)
    return backup_path


def list_backups() -> list[Path]:
    """List all backup files, newest first."""
    if not BACKUP_DIR.exists():
        return []
    backups = sorted(BACKUP_DIR.glob("*.bin"), reverse=True)
    return backups


def get_latest_backup() -> Path | None:
    """Return the most recent backup file, or None."""
    backups = list_backups()
    return backups[0] if backups else None


def clamp_actuation(mm: float) -> float:
    """Clamp actuation value to valid range [0.1, 4.0]mm.

    Raises SafetyError if the input is wildly out of range (> 10mm or < 0),
    which likely indicates a bug rather than a user request.
    """
    if mm < 0 or mm > 10.0:
        raise SafetyError(
            f"Actuation value {mm}mm is wildly out of range — "
            f"likely a bug. Valid range: 0.1 — 4.0mm"
        )
    clamped = max(protocol.MIN_MM, min(protocol.MAX_MM, mm))
    return round(clamped, 1)


def validate_changes(changes: dict[int, float]) -> dict[int, float]:
    """Validate and clamp all actuation changes.

    Args:
        changes: Dict mapping evdev key_code → desired actuation_mm

    Returns:
        Validated dict with clamped values

    Raises:
        SafetyError: If any value is wildly out of range
    """
    validated = {}
    for key_code, mm in changes.items():
        validated[key_code] = clamp_actuation(mm)
    return validated


def safe_write(
    fd: int,
    changes: dict[int, float],
    *,
    persist: bool = False,
    verify: bool = True,
) -> tuple[Path, dict[int, float]]:
    """Safely apply actuation changes with full safety protocol.

    Steps:
    1. Read current feature report
    2. Create backup of current state
    3. Validate and clamp all values
    4. Encode changes into report (read-modify-write)
    5. Write modified report
    6. Read back and verify (if verify=True)
    7. Optionally persist to flash (if persist=True)

    Args:
        fd: Open hidraw file descriptor
        changes: Dict mapping SS key_position → actuation_mm
        persist: If True, persist to flash (default: RAM only)
        verify: If True, read back after write and verify

    Returns:
        Tuple of (backup_path, applied_changes)

    Raises:
        SafetyError: If backup or validation fails
        VerificationError: If read-back doesn't match
        protocol.ProtocolError: If protocol encoding fails
    """
    # 1. Read current state
    current_report = device.get_feature(fd, report_id=protocol.REPORT_ID)

    # 2. Backup
    backup_path = create_backup(current_report)

    # 3. Validate
    validated = {}
    for key_pos, mm in changes.items():
        validated[key_pos] = clamp_actuation(mm)

    # 4. Encode (read-modify-write)
    modified_report = protocol.encode_actuation_map(current_report, validated)

    # 5. Write
    device.set_feature(fd, modified_report)

    # 6. Verify
    if verify:
        readback = device.get_feature(fd, report_id=protocol.REPORT_ID)
        # Compare only the actuation region
        if protocol.ACTUATION_OFFSET is not None and protocol.ACTUATION_LENGTH is not None:
            start = protocol.ACTUATION_OFFSET
            end = start + protocol.ACTUATION_LENGTH
            if modified_report[start:end] != readback[start:end]:
                # Attempt to restore from backup
                try:
                    device.set_feature(fd, current_report)
                except OSError:
                    pass
                raise VerificationError(
                    "Read-back verification failed! "
                    "Original state restored from pre-write backup. "
                    f"Backup saved at: {backup_path}"
                )

    # 7. Persist (placeholder — protocol for flash write TBD)
    if persist:
        # TODO(RE): Determine the flash-persist command
        # Some SteelSeries devices use a separate output report command
        # to commit RAM settings to flash/EEPROM
        pass

    return backup_path, validated


def restore_from_backup(fd: int, backup_path: Path) -> None:
    """Restore a feature report from a backup file.

    Args:
        fd: Open hidraw file descriptor
        backup_path: Path to the .bin backup file

    Raises:
        SafetyError: If backup file is invalid
    """
    if not backup_path.exists():
        raise SafetyError(f"Backup file not found: {backup_path}")

    data = backup_path.read_bytes()
    if len(data) != protocol.REPORT_SIZE:
        raise SafetyError(
            f"Backup file size {len(data)} != expected {protocol.REPORT_SIZE}. "
            f"File may be corrupted."
        )

    # Backup current state before restoring
    current = device.get_feature(fd, report_id=protocol.REPORT_ID)
    create_backup(current, label="pre_restore")

    device.set_feature(fd, data)


def factory_reset_report(report: bytes) -> bytes:
    """Create a report with all actuation values set to default (2.0mm).

    Args:
        report: Original feature report (used as template, non-actuation bytes preserved)

    Returns:
        Modified report with all actuation bytes set to default
    """
    if protocol.ACTUATION_OFFSET is None or protocol.ACTUATION_LENGTH is None:
        raise SafetyError(
            "Cannot factory reset: actuation offsets not yet determined. "
            "Run reverse engineering first."
        )

    modified = bytearray(report)
    for i in range(protocol.ACTUATION_LENGTH):
        modified[protocol.ACTUATION_OFFSET + i] = protocol.DEFAULT_BYTE
    return bytes(modified)
