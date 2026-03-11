"""QWERTZ finger mapping and physical neighbor map for error detection.

Key point: evdev key codes follow the US QWERTY physical layout names.
On a QWERTZ keyboard:
  KEY_Y (code 21) is physically the Z key (top-right of left hand)
  KEY_Z (code 44) is physically the Y key (bottom-left of right pinky area)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# FINGER_MAP: evdev key_code -> (finger_name, qwertz_label)
# ---------------------------------------------------------------------------
# Finger names reflect which finger presses the key on a QWERTZ 10-finger layout.
# QWERTZ label is what is printed on the keycap (German layout).
#
# evdev code reference (relevant subset):
#   1=Esc  2=1  3=2  4=3  5=4  6=5  7=6  8=7  9=8  10=9  11=0  12=ß  13=´
#   14=BS  15=Tab  16=Q  17=W  18=E  19=R  20=T  21=Y(QWERTZ:Z)  22=U
#   23=I  24=O  25=P  26=Ü  27=+  28=Enter
#   30=A  31=S  32=D  33=F  34=G  35=H  36=J  37=K  38=L  39=Ö  40=Ä  41=^  43=#
#   44=Z(QWERTZ:Y)  45=X  46=C  47=V  48=B  49=N  50=M  51=,  52=.  53=-
#   57=Space  86=<
# ---------------------------------------------------------------------------

FINGER_MAP: dict[int, tuple[str, str]] = {
    # --- Left Pinky ---
    41: ("left_pinky", "^"),      # ^ (top-left dead key)
    2:  ("left_pinky", "1"),      # 1
    16: ("left_pinky", "Q"),      # Q
    30: ("left_pinky", "A"),      # A
    86: ("left_pinky", "<"),      # < (ISO extra key, left of Z)
    44: ("left_pinky", "Y"),      # KEY_Z → physically Y on QWERTZ (bottom row)
    15: ("left_pinky", "Tab"),    # Tab

    # --- Left Ring ---
    3:  ("left_ring", "2"),       # 2
    17: ("left_ring", "W"),       # W
    31: ("left_ring", "S"),       # S
    45: ("left_ring", "X"),       # X

    # --- Left Middle ---
    4:  ("left_middle", "3"),     # 3
    18: ("left_middle", "E"),     # E
    32: ("left_middle", "D"),     # D
    46: ("left_middle", "C"),     # C

    # --- Left Index ---
    5:  ("left_index", "4"),      # 4
    6:  ("left_index", "5"),      # 5
    19: ("left_index", "R"),      # R
    20: ("left_index", "T"),      # T
    33: ("left_index", "F"),      # F
    34: ("left_index", "G"),      # G
    47: ("left_index", "V"),      # V
    48: ("left_index", "B"),      # B

    # --- Right Index ---
    7:  ("right_index", "6"),     # 6
    8:  ("right_index", "7"),     # 7
    21: ("right_index", "Z"),     # KEY_Y → physically Z on QWERTZ
    22: ("right_index", "U"),     # U
    35: ("right_index", "H"),     # H
    36: ("right_index", "J"),     # J
    49: ("right_index", "N"),     # N
    50: ("right_index", "M"),     # M

    # --- Right Middle ---
    9:  ("right_middle", "8"),    # 8
    23: ("right_middle", "I"),    # I
    37: ("right_middle", "K"),    # K
    51: ("right_middle", ","),    # ,

    # --- Right Ring ---
    10: ("right_ring", "9"),      # 9
    24: ("right_ring", "O"),      # O
    38: ("right_ring", "L"),      # L
    52: ("right_ring", "."),      # .

    # --- Right Pinky ---
    11: ("right_pinky", "0"),     # 0
    12: ("right_pinky", "ß"),     # ß
    13: ("right_pinky", "´"),     # ´ (dead key)
    25: ("right_pinky", "P"),     # P
    26: ("right_pinky", "Ü"),     # Ü
    27: ("right_pinky", "+"),     # +
    39: ("right_pinky", "Ö"),     # Ö
    40: ("right_pinky", "Ä"),     # Ä
    43: ("right_pinky", "#"),     # #
    53: ("right_pinky", "-"),     # -
    14: ("right_pinky", "Backspace"),  # Backspace
    28: ("right_pinky", "Enter"),     # Enter

    # --- Thumbs (both, mapped to "thumb") ---
    57: ("thumb", "Space"),       # Space
}

# ---------------------------------------------------------------------------
# NEIGHBORS: physical adjacency map (symmetric)
# Key codes that are physically adjacent on the QWERTZ keyboard.
# Used to detect likely "fat finger" errors (pressed wrong but nearby key).
# ---------------------------------------------------------------------------
# Build as a raw dict of sets, then enforce symmetry below.
_NEIGHBOR_RAW: dict[int, set[int]] = {
    # Number row
    2:  {3, 16, 17},           # 1 neighbors: 2(neighboring num), Q, W
    3:  {2, 4, 16, 17, 18},    # 2 neighbors: 1, 3, Q, W, E
    4:  {3, 5, 17, 18, 19},    # 3 neighbors: 2, 4, W, E, R
    5:  {4, 6, 18, 19, 20},    # 4 neighbors: 3, 5, E, R, T
    6:  {5, 7, 19, 20, 21},    # 5 neighbors: 4, 6, R, T, Z(KEY_Y)
    7:  {6, 8, 20, 21, 22},    # 6 neighbors: 5, 7, T, Z, U
    8:  {7, 9, 21, 22, 23},    # 7 neighbors: 6, 8, Z, U, I
    9:  {8, 10, 22, 23, 24},   # 8 neighbors: 7, 9, U, I, O
    10: {9, 11, 23, 24, 25},   # 9 neighbors: 8, 0, I, O, P
    11: {10, 12, 24, 25, 26},  # 0 neighbors: 9, ß, O, P, Ü
    12: {11, 13, 25, 26, 27},  # ß neighbors: 0, ´, P, Ü, +
    13: {12, 26, 27},          # ´ neighbors: ß, Ü, +

    # Top letter row (QWERTZ)
    15: {16, 30},              # Tab neighbors: Q, A
    16: {15, 17, 30, 31},      # Q neighbors: Tab, W, A, S
    17: {16, 18, 30, 31, 32},  # W neighbors: Q, E, A, S, D
    18: {17, 19, 31, 32, 33},  # E neighbors: W, R, S, D, F
    19: {18, 20, 32, 33, 34},  # R neighbors: E, T, D, F, G
    20: {19, 21, 33, 34, 35},  # T neighbors: R, Z(KEY_Y), F, G, H
    21: {20, 22, 34, 35, 36},  # Z(KEY_Y) neighbors: T, U, G, H, J
    22: {21, 23, 35, 36, 37},  # U neighbors: Z, I, H, J, K
    23: {22, 24, 36, 37, 38},  # I neighbors: U, O, J, K, L
    24: {23, 25, 37, 38, 39},  # O neighbors: I, P, K, L, Ö
    25: {24, 26, 38, 39, 40},  # P neighbors: O, Ü, L, Ö, Ä
    26: {25, 27, 39, 40, 43},  # Ü neighbors: P, +, Ö, Ä, #
    27: {26, 28, 40, 43},      # + neighbors: Ü, Enter, Ä, #

    # Home row
    30: {15, 16, 31, 44, 45},  # A neighbors: Tab, Q, S, Y(KEY_Z), X
    31: {30, 32, 16, 17, 45, 46},  # S neighbors: A, D, Q, W, X, C
    32: {31, 33, 17, 18, 46, 47},  # D neighbors: S, F, W, E, C, V
    33: {32, 34, 18, 19, 47, 48},  # F neighbors: D, G, E, R, V, B
    34: {33, 35, 19, 20, 48, 49},  # G neighbors: F, H, R, T, B, N
    35: {34, 36, 20, 21, 49, 50},  # H neighbors: G, J, T, Z, N, M
    36: {35, 37, 21, 22, 50, 51},  # J neighbors: H, K, Z, U, M, ,
    37: {36, 38, 22, 23, 51, 52},  # K neighbors: J, L, U, I, ,, .
    38: {37, 39, 23, 24, 52, 53},  # L neighbors: K, Ö, I, O, ., -
    39: {38, 40, 24, 25, 53},      # Ö neighbors: L, Ä, O, P, -
    40: {39, 43, 25, 26},          # Ä neighbors: Ö, #, P, Ü
    43: {40, 27, 26, 28},          # # neighbors: Ä, +, Ü, Enter

    # Bottom row
    86: {44, 30},              # < (ISO) neighbors: Y(KEY_Z), A
    44: {86, 45, 30, 31},      # Y(KEY_Z) neighbors: <, X, A, S
    45: {44, 46, 31, 32},      # X neighbors: Y, C, S, D
    46: {45, 47, 32, 33},      # C neighbors: X, V, D, F
    47: {46, 48, 33, 34},      # V neighbors: C, B, F, G
    48: {47, 49, 34, 35, 57},  # B neighbors: V, N, G, H, Space
    49: {48, 50, 35, 36, 57},  # N neighbors: B, M, H, J, Space
    50: {49, 51, 36, 37, 57},  # M neighbors: N, ,, J, K, Space
    51: {50, 52, 37, 38, 57},  # , neighbors: M, ., K, L, Space
    52: {51, 53, 38, 39, 57},  # . neighbors: ,, -, L, Ö, Space
    53: {52, 38, 39},          # - neighbors: ., L, Ö

    # Space
    57: {48, 49, 50, 51, 52},  # Space neighbors: B, N, M, ,, .

    # Enter/Backspace
    28: {27, 43},              # Enter neighbors: +, #
    14: {13, 27},              # Backspace neighbors: ´, +
}


def _build_symmetric_neighbors(raw: dict[int, set[int]]) -> dict[int, set[int]]:
    """Ensure the neighbor map is fully symmetric."""
    result: dict[int, set[int]] = {k: set(v) for k, v in raw.items()}
    for key, neighbors in raw.items():
        for neighbor in neighbors:
            if neighbor not in result:
                result[neighbor] = set()
            result[neighbor].add(key)
    return result


NEIGHBORS: dict[int, set[int]] = _build_symmetric_neighbors(_NEIGHBOR_RAW)

# ---------------------------------------------------------------------------
# FINGER_NAMES: canonical ordered list (left to right, anatomical order)
# ---------------------------------------------------------------------------
FINGER_NAMES: list[str] = [
    "left_pinky",
    "left_ring",
    "left_middle",
    "left_index",
    "thumb",
    "right_index",
    "right_middle",
    "right_ring",
    "right_pinky",
]

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def get_finger(key_code: int) -> str | None:
    """Return the finger name for a key code, or None if not mapped."""
    entry = FINGER_MAP.get(key_code)
    return entry[0] if entry is not None else None


def get_label(key_code: int) -> str | None:
    """Return the QWERTZ keycap label for a key code, or None if not mapped."""
    entry = FINGER_MAP.get(key_code)
    return entry[1] if entry is not None else None


def get_neighbors(key_code: int) -> set[int]:
    """Return the set of physically adjacent key codes (empty set if unknown)."""
    return NEIGHBORS.get(key_code, set())


def is_neighbor(key_a: int, key_b: int) -> bool:
    """Return True if key_a and key_b are physically adjacent on the keyboard."""
    return key_b in NEIGHBORS.get(key_a, set())


def get_keys_for_finger(finger: str) -> list[int]:
    """Return all key codes assigned to a given finger name."""
    return [code for code, (f, _) in FINGER_MAP.items() if f == finger]
