"""High-level actuation control — bridge between recommendations and HID.

Converts TypoTuner's recommendation output (list of dicts with evdev key_codes
and mm values) into actual HID writes to the SteelSeries Apex Pro TKL 2023.
"""

from __future__ import annotations

from .. import qwertz
from ..storage import Storage
from . import device, keymap, protocol, safety


class ActuationController:
    """Manages actuation point changes for the keyboard."""

    def __init__(self, storage: Storage | None = None):
        self._storage = storage
        self._fd: int | None = None
        self._device_path: str | None = None

    def connect(self) -> dict:
        """Find and connect to the keyboard.

        Returns:
            Device info dict

        Raises:
            device.DeviceNotFoundError: If keyboard not found
            device.DevicePermissionError: If no permissions
        """
        self._device_path = device.find_device()
        self._fd = device.open_device(self._device_path)
        return device.get_device_info(self._device_path)

    def disconnect(self) -> None:
        """Close the device connection."""
        if self._fd is not None:
            device.close_device(self._fd)
            self._fd = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    @property
    def connected(self) -> bool:
        return self._fd is not None

    def read_current_actuation(self) -> dict[int, float] | None:
        """Read current per-key actuation from the keyboard.

        Returns:
            Dict mapping SS key_position → actuation_mm,
            or None if protocol offsets are not yet known.
        """
        self._require_connected()
        report = device.get_feature(self._fd, report_id=protocol.REPORT_ID)
        return protocol.decode_actuation_map(report)

    def read_raw_report(self) -> bytes:
        """Read the raw feature report for RE/debugging."""
        self._require_connected()
        return device.get_feature(self._fd, report_id=protocol.REPORT_ID)

    def diff_current(self) -> list[tuple[int, int, int]]:
        """Read two reports (for Fn+O/I diffing during RE).

        Usage: call once before Fn+O/I, then call again after.
        Compare the two returns with protocol.diff_reports().
        """
        self._require_connected()
        return device.get_feature(self._fd, report_id=protocol.REPORT_ID)

    def preview_changes(
        self, recommendations: list[dict]
    ) -> list[dict]:
        """Preview what would change without writing anything.

        Args:
            recommendations: Output from recommender.generate_recommendations()

        Returns:
            List of dicts with: key_name, key_code, current_mm, new_mm, ss_position
        """
        changes = []
        current = self.read_current_actuation() if self.connected else None

        for rec in recommendations:
            key_code = rec["key_code"]
            ss_pos = keymap.evdev_to_ss(key_code)
            if ss_pos is None:
                continue

            current_mm = rec.get("current_mm", protocol.DEFAULT_MM)
            if current is not None and ss_pos in current:
                current_mm = current[ss_pos]

            new_mm = safety.clamp_actuation(rec["recommended_mm"])
            if abs(new_mm - current_mm) < 0.05:
                continue

            changes.append({
                "key_name": rec["key_name"],
                "key_code": key_code,
                "ss_position": ss_pos,
                "current_mm": current_mm,
                "new_mm": new_mm,
                "reason": rec.get("reason", ""),
                "confidence": rec.get("confidence", 0.0),
            })

        return changes

    def apply_recommendations(
        self,
        recommendations: list[dict],
        *,
        persist: bool = False,
    ) -> tuple[safety.Path, list[dict]]:
        """Apply actuation recommendations to the keyboard.

        Args:
            recommendations: Output from recommender.generate_recommendations()
            persist: If True, persist to flash. Default: RAM only.

        Returns:
            Tuple of (backup_path, list of applied changes)
        """
        self._require_connected()

        # Convert evdev key_codes to SS positions
        ss_changes: dict[int, float] = {}
        applied = []
        for rec in recommendations:
            key_code = rec["key_code"]
            ss_pos = keymap.evdev_to_ss(key_code)
            if ss_pos is None:
                continue

            new_mm = safety.clamp_actuation(rec["recommended_mm"])
            ss_changes[ss_pos] = new_mm
            applied.append({
                "key_code": key_code,
                "key_name": rec["key_name"],
                "ss_position": ss_pos,
                "previous_mm": rec.get("current_mm", protocol.DEFAULT_MM),
                "new_mm": new_mm,
            })

        if not ss_changes:
            raise ValueError("No applicable changes — all keys unmapped or unchanged")

        # Write with full safety protocol
        backup_path, validated = safety.safe_write(
            self._fd, ss_changes, persist=persist
        )

        # Record in DB if storage available
        if self._storage is not None:
            for change in applied:
                self._storage.record_actuation_change(
                    key_code=change["key_code"],
                    previous_mm=change["previous_mm"],
                    new_mm=change["new_mm"],
                    source="auto",
                    persisted=persist,
                )

        return backup_path, applied

    def apply_single_key(
        self,
        key_code: int,
        mm: float,
        *,
        persist: bool = False,
    ) -> tuple[safety.Path, float]:
        """Set actuation for a single key.

        Args:
            key_code: evdev key code
            mm: Target actuation in mm
            persist: Persist to flash

        Returns:
            Tuple of (backup_path, actual_mm_applied)
        """
        self._require_connected()

        ss_pos = keymap.evdev_to_ss(key_code)
        if ss_pos is None:
            label = keymap.evdev_to_label(key_code)
            raise ValueError(f"Key {label} (evdev {key_code}) has no SteelSeries mapping")

        clamped = safety.clamp_actuation(mm)
        backup_path, validated = safety.safe_write(
            self._fd, {ss_pos: clamped}, persist=persist
        )

        if self._storage is not None:
            self._storage.record_actuation_change(
                key_code=key_code,
                previous_mm=protocol.DEFAULT_MM,
                new_mm=clamped,
                source="manual",
                persisted=persist,
            )

        return backup_path, clamped

    def restore(self, backup_path: safety.Path | None = None) -> safety.Path:
        """Restore from a backup file.

        Args:
            backup_path: Specific backup to restore. If None, uses latest.

        Returns:
            Path of the backup that was restored
        """
        self._require_connected()

        if backup_path is None:
            backup_path = safety.get_latest_backup()
            if backup_path is None:
                raise FileNotFoundError("No backups found")

        safety.restore_from_backup(self._fd, backup_path)
        return backup_path

    def factory_reset(self, *, persist: bool = False) -> safety.Path:
        """Reset all keys to default actuation (2.0mm).

        Returns:
            Backup path (of the state before reset)
        """
        self._require_connected()

        current = device.get_feature(self._fd, report_id=protocol.REPORT_ID)
        backup_path = safety.create_backup(current, label="pre_factory_reset")
        reset_report = safety.factory_reset_report(current)
        device.set_feature(self._fd, reset_report)

        if persist:
            pass  # TODO(RE): flash persist command

        return backup_path

    def _require_connected(self) -> None:
        if self._fd is None:
            raise RuntimeError("Not connected to device. Call connect() first.")
