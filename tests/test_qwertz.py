"""Tests for typotuner.qwertz — QWERTZ finger map and neighbor detection."""

from typotuner import qwertz


class TestFingerMap:
    def test_all_fingers_represented(self):
        """Every finger in FINGER_NAMES should have at least one key."""
        for finger in qwertz.FINGER_NAMES:
            keys = qwertz.get_keys_for_finger(finger)
            assert len(keys) > 0, f"No keys for {finger}"

    def test_yz_swap_z_physical(self):
        """KEY_Y (21) should map to 'Z' on QWERTZ (right_index)."""
        assert qwertz.get_label(21) == "Z"
        assert qwertz.get_finger(21) == "right_index"

    def test_yz_swap_y_physical(self):
        """KEY_Z (44) should map to 'Y' on QWERTZ (left_pinky)."""
        assert qwertz.get_label(44) == "Y"
        assert qwertz.get_finger(44) == "left_pinky"

    def test_home_row_keys(self):
        """Home row ASDF should be on correct fingers."""
        assert qwertz.get_finger(30) == "left_pinky"   # A
        assert qwertz.get_finger(31) == "left_ring"    # S
        assert qwertz.get_finger(32) == "left_middle"  # D
        assert qwertz.get_finger(33) == "left_index"   # F

    def test_home_row_right(self):
        """Home row HJKL should be on correct fingers."""
        assert qwertz.get_finger(35) == "right_index"   # H
        assert qwertz.get_finger(36) == "right_index"   # J
        assert qwertz.get_finger(37) == "right_middle"  # K
        assert qwertz.get_finger(38) == "right_ring"    # L

    def test_space_is_thumb(self):
        """Space (57) should be thumb."""
        assert qwertz.get_finger(57) == "thumb"
        assert qwertz.get_label(57) == "Space"

    def test_unknown_key(self):
        """Unknown key code returns None."""
        assert qwertz.get_finger(999) is None
        assert qwertz.get_label(999) is None

    def test_backspace_is_right_pinky(self):
        """Backspace (14) mapped to right_pinky."""
        assert qwertz.get_finger(14) == "right_pinky"

    def test_german_special_keys(self):
        """Umlauts should be on right_pinky."""
        assert qwertz.get_finger(26) == "right_pinky"  # Ü
        assert qwertz.get_finger(39) == "right_pinky"  # Ö
        assert qwertz.get_finger(40) == "right_pinky"  # Ä


class TestNeighbors:
    def test_neighbors_symmetric(self):
        """If A is neighbor of B, B must be neighbor of A."""
        for key, neighbors in qwertz.NEIGHBORS.items():
            for n in neighbors:
                assert key in qwertz.NEIGHBORS.get(n, set()), \
                    f"Asymmetric: {key} -> {n} but {n} -/-> {key}"

    def test_sd_neighbors(self):
        """S (31) and D (32) should be neighbors."""
        assert qwertz.is_neighbor(31, 32)
        assert qwertz.is_neighbor(32, 31)

    def test_non_neighbors(self):
        """Q (16) and M (50) should NOT be neighbors."""
        assert not qwertz.is_neighbor(16, 50)

    def test_yz_swap_neighbors(self):
        """Z (KEY_Y=21) should be neighbor of T (20) and U (22)."""
        assert qwertz.is_neighbor(21, 20)  # Z-T
        assert qwertz.is_neighbor(21, 22)  # Z-U

    def test_get_neighbors_returns_set(self):
        """get_neighbors should return a set."""
        n = qwertz.get_neighbors(30)  # A
        assert isinstance(n, set)
        assert len(n) > 0

    def test_unknown_key_no_neighbors(self):
        """Unknown key should have empty neighbor set."""
        assert qwertz.get_neighbors(999) == set()
