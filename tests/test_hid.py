"""Tests for typotuner.hid — protocol, keymap, safety, device, and storage integration."""

from unittest.mock import patch

import pytest

from typotuner.hid import protocol, keymap, safety, device
from typotuner.hid.protocol import ProtocolError
from typotuner.hid.safety import SafetyError
from typotuner.storage import Storage


# ── protocol.py ──────────────────────────────────────────────────────────


class TestMmToByte:
    def test_min_value(self):
        assert protocol.mm_to_byte(0.1) == 0x00

    def test_max_value(self):
        assert protocol.mm_to_byte(4.0) == 0x27

    def test_default_value(self):
        assert protocol.mm_to_byte(2.0) == 0x13

    def test_step_values(self):
        assert protocol.mm_to_byte(0.2) == 0x01
        assert protocol.mm_to_byte(0.5) == 0x04
        assert protocol.mm_to_byte(1.0) == 0x09

    def test_below_range_raises(self):
        with pytest.raises(ProtocolError, match="out of range"):
            protocol.mm_to_byte(0.0)

    def test_above_range_raises(self):
        with pytest.raises(ProtocolError, match="out of range"):
            protocol.mm_to_byte(4.2)

    def test_negative_raises(self):
        with pytest.raises(ProtocolError, match="out of range"):
            protocol.mm_to_byte(-1.0)

    def test_tolerance_just_within(self):
        result = protocol.mm_to_byte(0.1 - 0.0005)
        assert result == 0x00
        result = protocol.mm_to_byte(4.0 + 0.0005)
        assert result == 0x27


class TestByteToMm:
    def test_min_byte(self):
        assert protocol.byte_to_mm(0x00) == 0.1

    def test_max_byte(self):
        assert protocol.byte_to_mm(0x27) == 4.0

    def test_default_byte(self):
        assert protocol.byte_to_mm(0x13) == 2.0

    def test_above_range_raises(self):
        with pytest.raises(ProtocolError, match="out of range"):
            protocol.byte_to_mm(0x28)

    def test_negative_raises(self):
        with pytest.raises(ProtocolError, match="out of range"):
            protocol.byte_to_mm(-1)

    def test_large_value_raises(self):
        with pytest.raises(ProtocolError, match="out of range"):
            protocol.byte_to_mm(0xFF)


class TestRoundTrip:
    @pytest.mark.parametrize("mm", [0.1, 0.5, 1.0, 2.0, 3.5, 4.0])
    def test_mm_round_trip(self, mm):
        assert protocol.byte_to_mm(protocol.mm_to_byte(mm)) == mm

    @pytest.mark.parametrize("byte_val", [0x00, 0x01, 0x10, 0x13, 0x26, 0x27])
    def test_byte_round_trip(self, byte_val):
        assert protocol.mm_to_byte(protocol.byte_to_mm(byte_val)) == byte_val


class TestDiffReports:
    def test_identical_reports(self):
        a = bytes(100)
        assert protocol.diff_reports(a, a) == []

    def test_single_diff(self):
        a = bytes(10)
        b = bytearray(10)
        b[5] = 0xFF
        diffs = protocol.diff_reports(a, bytes(b))
        assert diffs == [(5, 0x00, 0xFF)]

    def test_multiple_diffs(self):
        a = bytes(10)
        b = bytearray(10)
        b[0] = 1
        b[9] = 2
        diffs = protocol.diff_reports(a, bytes(b))
        assert len(diffs) == 2
        assert diffs[0] == (0, 0, 1)
        assert diffs[1] == (9, 0, 2)

    def test_different_lengths(self):
        a = bytes(5)
        b = bytearray(10)
        b[3] = 0x42
        diffs = protocol.diff_reports(a, bytes(b))
        assert diffs == [(3, 0x00, 0x42)]

    def test_empty_reports(self):
        assert protocol.diff_reports(b"", b"") == []


class TestFormatDiff:
    def test_empty_diff(self):
        assert protocol.format_diff([]) == "No differences found."

    def test_single_diff_format(self):
        diffs = [(0x0010, 0x00, 0x13)]
        result = protocol.format_diff(diffs)
        assert "1 differing" in result
        assert "0x0010" in result
        assert "0.1mm" in result
        assert "2.0mm" in result

    def test_out_of_range_shows_question_mark(self):
        diffs = [(0, 0xFF, 0x00)]
        result = protocol.format_diff(diffs)
        assert "?" in result
        assert "0.1mm" in result


# ── keymap.py ────────────────────────────────────────────────────────────


class TestEvdevToSs:
    def test_known_key(self):
        assert keymap.evdev_to_ss(30) == 0x04

    def test_space(self):
        assert keymap.evdev_to_ss(57) == 0x2C

    def test_escape(self):
        assert keymap.evdev_to_ss(1) == 0x29

    def test_unknown_key_returns_none(self):
        assert keymap.evdev_to_ss(999) is None

    def test_yz_swap(self):
        assert keymap.evdev_to_ss(21) == 0x1C
        assert keymap.evdev_to_ss(44) == 0x1D


class TestSsToEvdev:
    def test_known_position(self):
        assert keymap.ss_to_evdev(0x04) == 30

    def test_unknown_position_returns_none(self):
        assert keymap.ss_to_evdev(0xFF) is None

    def test_reverse_consistency(self):
        for evdev_code, ss_pos in keymap.EVDEV_TO_SS.items():
            assert keymap.SS_TO_EVDEV[ss_pos] == evdev_code


class TestValidateKeymap:
    def test_returns_list(self):
        result = keymap.validate_keymap()
        assert isinstance(result, list)

    def test_warnings_are_strings(self):
        for w in keymap.validate_keymap():
            assert isinstance(w, str)
            assert "no SteelSeries mapping" in w


# ── safety.py ────────────────────────────────────────────────────────────


class TestClampActuation:
    def test_within_range(self):
        assert safety.clamp_actuation(2.0) == 2.0

    def test_clamp_low(self):
        assert safety.clamp_actuation(0.05) == 0.1

    def test_clamp_high(self):
        assert safety.clamp_actuation(5.0) == 4.0

    def test_at_min_boundary(self):
        assert safety.clamp_actuation(0.1) == 0.1

    def test_at_max_boundary(self):
        assert safety.clamp_actuation(4.0) == 4.0

    def test_wildly_negative_raises(self):
        with pytest.raises(SafetyError, match="wildly out of range"):
            safety.clamp_actuation(-1.0)

    def test_wildly_high_raises(self):
        with pytest.raises(SafetyError, match="wildly out of range"):
            safety.clamp_actuation(11.0)

    def test_zero_clamps_to_min(self):
        assert safety.clamp_actuation(0.0) == 0.1

    def test_exactly_ten_clamps(self):
        assert safety.clamp_actuation(10.0) == 4.0

    def test_rounding(self):
        assert safety.clamp_actuation(2.06) == 2.1


class TestValidateChanges:
    def test_valid_changes(self):
        changes = {30: 1.5, 31: 2.0}
        result = safety.validate_changes(changes)
        assert result == {30: 1.5, 31: 2.0}

    def test_clamps_values(self):
        changes = {30: 0.05, 31: 5.0}
        result = safety.validate_changes(changes)
        assert result[30] == 0.1
        assert result[31] == 4.0

    def test_empty_changes(self):
        assert safety.validate_changes({}) == {}

    def test_wildly_out_of_range_raises(self):
        with pytest.raises(SafetyError):
            safety.validate_changes({30: -5.0})


class TestCreateBackup:
    def test_creates_file(self, tmp_path):
        with patch.object(safety, "BACKUP_DIR", tmp_path / "backups"):
            report = bytes(644)
            path = safety.create_backup(report, label="test")
            assert path.exists()
            assert path.read_bytes() == report

    def test_file_naming(self, tmp_path):
        with patch.object(safety, "BACKUP_DIR", tmp_path / "backups"):
            path = safety.create_backup(b"\x00" * 10, label="actuation")
            assert "actuation_" in path.name
            assert path.suffix == ".bin"

    def test_custom_label(self, tmp_path):
        with patch.object(safety, "BACKUP_DIR", tmp_path / "backups"):
            path = safety.create_backup(b"\x00", label="pre_restore")
            assert "pre_restore_" in path.name

    def test_creates_parent_dirs(self, tmp_path):
        deep_path = tmp_path / "a" / "b" / "backups"
        with patch.object(safety, "BACKUP_DIR", deep_path):
            path = safety.create_backup(b"\x00")
            assert path.exists()
            assert deep_path.exists()


class TestListBackups:
    def test_empty_dir(self, tmp_path):
        with patch.object(safety, "BACKUP_DIR", tmp_path / "nonexistent"):
            assert safety.list_backups() == []

    def test_lists_bin_files(self, tmp_path):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        (backup_dir / "a.bin").write_bytes(b"\x00")
        (backup_dir / "b.bin").write_bytes(b"\x00")
        (backup_dir / "c.txt").write_text("not a backup")
        with patch.object(safety, "BACKUP_DIR", backup_dir):
            backups = safety.list_backups()
            assert len(backups) == 2
            assert all(p.suffix == ".bin" for p in backups)

    def test_sorted_newest_first(self, tmp_path):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        (backup_dir / "actuation_20240101_120000.bin").write_bytes(b"\x00")
        (backup_dir / "actuation_20240102_120000.bin").write_bytes(b"\x00")
        with patch.object(safety, "BACKUP_DIR", backup_dir):
            backups = safety.list_backups()
            assert backups[0].name > backups[1].name


# ── device.py ────────────────────────────────────────────────────────────


class TestIoctlConstants:
    def test_hidiocgfeature_644(self):
        code = device._hidiocgfeature(644)
        assert isinstance(code, int)
        assert code != 0
        direction = (code >> device._IOC_DIRSHIFT) & 0x3
        assert direction == 3
        type_val = (code >> device._IOC_TYPESHIFT) & 0xFF
        assert type_val == ord("H")
        nr = (code >> device._IOC_NRSHIFT) & 0xFF
        assert nr == 0x07
        size = (code >> device._IOC_SIZESHIFT) & 0x3FFF
        assert size == 644

    def test_hidiocsfeature_644(self):
        code = device._hidiocsfeature(644)
        direction = (code >> device._IOC_DIRSHIFT) & 0x3
        assert direction == 3
        type_val = (code >> device._IOC_TYPESHIFT) & 0xFF
        assert type_val == ord("H")
        nr = (code >> device._IOC_NRSHIFT) & 0xFF
        assert nr == 0x06
        size = (code >> device._IOC_SIZESHIFT) & 0x3FFF
        assert size == 644

    def test_get_set_differ(self):
        assert device._hidiocgfeature(644) != device._hidiocsfeature(644)

    def test_different_sizes(self):
        assert device._hidiocgfeature(64) != device._hidiocgfeature(644)


# ── storage.py actuation history ─────────────────────────────────────────


class TestRecordActuationChange:
    def test_basic_record(self, tmp_db):
        tmp_db.record_actuation_change(30, previous_mm=2.0, new_mm=1.5)
        history = tmp_db.get_actuation_history()
        assert len(history) == 1
        assert history[0]["key_code"] == 30
        assert history[0]["previous_mm"] == 2.0
        assert history[0]["new_mm"] == 1.5

    def test_default_source(self, tmp_db):
        tmp_db.record_actuation_change(30, 2.0, 1.5)
        history = tmp_db.get_actuation_history()
        assert history[0]["source"] == "auto"

    def test_custom_source(self, tmp_db):
        tmp_db.record_actuation_change(30, 2.0, 1.5, source="manual")
        history = tmp_db.get_actuation_history()
        assert history[0]["source"] == "manual"

    def test_persisted_flag(self, tmp_db):
        tmp_db.record_actuation_change(30, 2.0, 1.5, persisted=True)
        history = tmp_db.get_actuation_history()
        assert history[0]["persisted"] == 1

    def test_not_persisted_default(self, tmp_db):
        tmp_db.record_actuation_change(30, 2.0, 1.5)
        history = tmp_db.get_actuation_history()
        assert history[0]["persisted"] == 0

    def test_multiple_records(self, tmp_db):
        tmp_db.record_actuation_change(30, 2.0, 1.5)
        tmp_db.record_actuation_change(30, 1.5, 1.0)
        tmp_db.record_actuation_change(31, 2.0, 3.0)
        history = tmp_db.get_actuation_history()
        assert len(history) == 3

    def test_timestamp_present(self, tmp_db):
        tmp_db.record_actuation_change(30, 2.0, 1.5)
        history = tmp_db.get_actuation_history()
        assert history[0]["timestamp"] is not None
        assert len(history[0]["timestamp"]) > 0


class TestGetActuationHistory:
    def test_empty_history(self, tmp_db):
        assert tmp_db.get_actuation_history() == []

    def test_limit(self, tmp_db):
        for i in range(10):
            tmp_db.record_actuation_change(30, 2.0, 1.0 + i * 0.1)
        history = tmp_db.get_actuation_history(limit=3)
        assert len(history) == 3

    def test_newest_first(self, tmp_db):
        tmp_db.record_actuation_change(30, 2.0, 1.5, source="first")
        tmp_db.record_actuation_change(30, 1.5, 1.0, source="second")
        history = tmp_db.get_actuation_history()
        assert history[0]["source"] == "second"
        assert history[1]["source"] == "first"

    def test_default_limit(self, tmp_db):
        for i in range(60):
            tmp_db.record_actuation_change(30, 2.0, 1.0 + i * 0.01)
        history = tmp_db.get_actuation_history()
        assert len(history) == 50

    def test_cleared_by_reset(self, tmp_db):
        tmp_db.record_actuation_change(30, 2.0, 1.5)
        tmp_db.reset()
        assert tmp_db.get_actuation_history() == []


# ── oled.py ─────────────────────────────────────────────────────────────


class TestOledConstants:
    def test_dimensions(self):
        from typotuner.hid.oled import OLED_WIDTH, OLED_HEIGHT, OLED_DATA_SIZE
        assert OLED_WIDTH == 128
        assert OLED_HEIGHT == 40
        assert OLED_DATA_SIZE == 640
        assert OLED_WIDTH * OLED_HEIGHT // 8 == OLED_DATA_SIZE

    def test_report_size(self):
        from typotuner.hid.oled import OLED_REPORT_SIZE, OLED_DATA_SIZE
        # report_id(1) + cmd(1) + bitmap(640) + trailing(1) = 643
        assert OLED_REPORT_SIZE == 643
        assert OLED_REPORT_SIZE == 1 + 1 + OLED_DATA_SIZE + 1

    def test_protocol_constants(self):
        from typotuner.hid.oled import OLED_CMD, OLED_REPORT_ID
        assert OLED_CMD == 0x61
        assert OLED_REPORT_ID == 0x00


class TestSendImage:
    def test_correct_report_format(self):
        """Verify the report sent to set_feature has correct structure."""
        from typotuner.hid import oled

        captured = {}

        def mock_set_feature(fd, data):
            captured["fd"] = fd
            captured["data"] = data

        with patch.object(oled.device, "set_feature", mock_set_feature):
            bitmap = bytes(range(256)) * 2 + bytes(range(128))  # 640 bytes
            oled.send_image(42, bitmap)

        assert captured["fd"] == 42
        data = captured["data"]
        assert len(data) == 643
        assert data[0] == 0x00  # report ID
        assert data[1] == 0x61  # OLED command byte
        assert data[2 : 2 + 640] == bitmap  # bitmap payload
        assert data[-1] == 0x00  # trailing byte

    def test_wrong_size_raises(self):
        from typotuner.hid import oled

        with pytest.raises(ValueError, match="640 bytes"):
            oled.send_image(42, bytes(100))

    def test_empty_raises(self):
        from typotuner.hid import oled

        with pytest.raises(ValueError, match="640 bytes"):
            oled.send_image(42, b"")

    def test_too_large_raises(self):
        from typotuner.hid import oled

        with pytest.raises(ValueError, match="640 bytes"):
            oled.send_image(42, bytes(641))


class TestClearScreen:
    def test_sends_zero_bitmap(self):
        from typotuner.hid import oled

        captured = {}

        def mock_set_feature(fd, data):
            captured["data"] = data

        with patch.object(oled.device, "set_feature", mock_set_feature):
            oled.clear_screen(42)

        data = captured["data"]
        assert len(data) == 643
        assert data[0] == 0x00  # report ID
        assert data[1] == 0x61  # command
        assert data[2:-1] == bytes(640)  # all zeros = clear
        assert data[-1] == 0x00


class TestRenderText:
    def test_returns_correct_size(self):
        from typotuner.hid.oled import render_text, OLED_DATA_SIZE
        bitmap = render_text("Hello")
        assert len(bitmap) == OLED_DATA_SIZE

    def test_nonempty_for_text(self):
        from typotuner.hid.oled import render_text
        bitmap = render_text("Test")
        assert bitmap != bytes(640)  # should have some pixels set

    def test_empty_string_is_blank(self):
        from typotuner.hid.oled import render_text
        bitmap = render_text("")
        assert bitmap == bytes(640)

    def test_custom_font_size(self):
        from typotuner.hid.oled import render_text, OLED_DATA_SIZE
        bitmap = render_text("X", font_size=10)
        assert len(bitmap) == OLED_DATA_SIZE


class TestRenderMultiline:
    def test_returns_correct_size(self):
        from typotuner.hid.oled import render_multiline, OLED_DATA_SIZE
        bitmap = render_multiline(["Line 1", "Line 2"])
        assert len(bitmap) == OLED_DATA_SIZE

    def test_nonempty_for_text(self):
        from typotuner.hid.oled import render_multiline
        bitmap = render_multiline(["Hello", "World"])
        assert bitmap != bytes(640)

    def test_empty_lines(self):
        from typotuner.hid.oled import render_multiline
        bitmap = render_multiline([])
        assert bitmap == bytes(640)

    def test_many_lines_truncated(self):
        from typotuner.hid.oled import render_multiline, OLED_DATA_SIZE
        # More lines than can fit in 40px height
        lines = [f"Line {i}" for i in range(20)]
        bitmap = render_multiline(lines, font_size=12)
        assert len(bitmap) == OLED_DATA_SIZE


class TestImageToBitmap:
    def test_correct_size(self):
        from PIL import Image
        from typotuner.hid.oled import image_to_bitmap, OLED_DATA_SIZE
        img = Image.new("RGB", (256, 80), color=(255, 255, 255))
        bitmap = image_to_bitmap(img)
        assert len(bitmap) == OLED_DATA_SIZE

    def test_black_image(self):
        from PIL import Image
        from typotuner.hid.oled import image_to_bitmap
        img = Image.new("1", (128, 40), color=0)
        bitmap = image_to_bitmap(img)
        assert bitmap == bytes(640)

    def test_white_image(self):
        from PIL import Image
        from typotuner.hid.oled import image_to_bitmap
        img = Image.new("1", (128, 40), color=1)
        bitmap = image_to_bitmap(img)
        assert bitmap == bytes([0xFF] * 640)

    def test_resizes_from_larger(self):
        from PIL import Image
        from typotuner.hid.oled import image_to_bitmap, OLED_DATA_SIZE
        img = Image.new("L", (1920, 1080), color=128)
        bitmap = image_to_bitmap(img)
        assert len(bitmap) == OLED_DATA_SIZE
