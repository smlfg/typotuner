"""SQLite storage for TypoTuner.

DB path: ~/.local/share/typotuner/typotuner.db
Thread-safe via sqlite3 check_same_thread=False + threading.Lock.
"""

import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

from . import qwertz


def _db_path() -> Path:
    db_dir = Path.home() / ".local" / "share" / "typotuner"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "typotuner.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS key_stats (
    key_code        INTEGER PRIMARY KEY,
    key_name        TEXT NOT NULL,
    finger          TEXT,
    total_presses   INTEGER DEFAULT 0,
    total_errors    INTEGER DEFAULT 0,
    error_rate_ema  REAL DEFAULT 0.0,
    avg_dwell_ms    REAL DEFAULT 0.0,
    dwell_ema       REAL DEFAULT 0.0,
    avg_flight_ms   REAL DEFAULT 0.0,
    daily_presses   INTEGER DEFAULT 0,
    daily_errors    INTEGER DEFAULT 0,
    daily_date      TEXT,
    last_pressed    TIMESTAMP,
    first_seen      TIMESTAMP
);

CREATE TABLE IF NOT EXISTS typo_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TIMESTAMP NOT NULL,
    error_key_code  INTEGER NOT NULL,
    intended_key    INTEGER,
    correction_ms   INTEGER NOT NULL,
    error_type      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TIMESTAMP,
    ended_at        TIMESTAMP,
    total_keys      INTEGER DEFAULT 0,
    total_errors    INTEGER DEFAULT 0,
    device_name     TEXT
);

CREATE TABLE IF NOT EXISTS recommendations (
    key_code        INTEGER PRIMARY KEY,
    key_name        TEXT NOT NULL,
    current_mm      REAL DEFAULT 2.0,
    recommended_mm  REAL NOT NULL,
    reason          TEXT NOT NULL,
    confidence      REAL DEFAULT 0.0,
    generated_at    TIMESTAMP,
    applied         INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS actuation_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    key_code        INTEGER NOT NULL,
    previous_mm     REAL NOT NULL,
    new_mm          REAL NOT NULL,
    source          TEXT NOT NULL,
    persisted       INTEGER DEFAULT 0
);
"""

TYPO_RING_BUFFER_SIZE = 10_000


class Storage:
    """Thread-safe SQLite storage for TypoTuner."""

    def __init__(self, db_path: Path | None = None):
        self._path = db_path or _db_path()
        self._conn = sqlite3.connect(
            str(self._path),
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # --- Key Stats ---

    def record_keypress(self, key_code: int, dwell_ms: float = 0.0,
                        flight_ms: float = 0.0, is_error: bool = False) -> None:
        """Record a keypress, updating running stats with EMA."""
        now = datetime.now()
        now_iso = now.isoformat()
        today = now.strftime("%Y-%m-%d")
        key_name = qwertz.get_label(key_code) or f"KEY_{key_code}"
        finger = qwertz.get_finger(key_code)

        # EMA coefficients
        error_alpha = 0.05
        dwell_alpha = 0.05

        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM key_stats WHERE key_code = ?", (key_code,)
            ).fetchone()

            if row is None:
                # First time seeing this key
                error_ema = 1.0 if is_error else 0.0
                dwell_ema_val = dwell_ms
                self._conn.execute(
                    """INSERT INTO key_stats
                       (key_code, key_name, finger, total_presses, total_errors,
                        error_rate_ema, avg_dwell_ms, dwell_ema, avg_flight_ms,
                        daily_presses, daily_errors, daily_date, last_pressed, first_seen)
                       VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
                    (key_code, key_name, finger,
                     1 if is_error else 0,
                     error_ema, dwell_ms, dwell_ema_val, flight_ms,
                     1 if is_error else 0,
                     today, now_iso, now_iso),
                )
            else:
                total = row["total_presses"] + 1
                errors = row["total_errors"] + (1 if is_error else 0)
                # EMA update
                new_error_ema = error_alpha * (1.0 if is_error else 0.0) + (1 - error_alpha) * row["error_rate_ema"]
                new_dwell_ema = dwell_alpha * dwell_ms + (1 - dwell_alpha) * row["dwell_ema"] if dwell_ms > 0 else row["dwell_ema"]
                # Running average for dwell and flight
                new_avg_dwell = ((row["avg_dwell_ms"] * row["total_presses"]) + dwell_ms) / total if dwell_ms > 0 else row["avg_dwell_ms"]
                new_avg_flight = ((row["avg_flight_ms"] * row["total_presses"]) + flight_ms) / total if flight_ms > 0 else row["avg_flight_ms"]
                # Daily reset
                if row["daily_date"] == today:
                    daily_p = row["daily_presses"] + 1
                    daily_e = row["daily_errors"] + (1 if is_error else 0)
                else:
                    daily_p = 1
                    daily_e = 1 if is_error else 0

                self._conn.execute(
                    """UPDATE key_stats SET
                       total_presses = ?, total_errors = ?,
                       error_rate_ema = ?, avg_dwell_ms = ?,
                       dwell_ema = ?, avg_flight_ms = ?,
                       daily_presses = ?, daily_errors = ?,
                       daily_date = ?, last_pressed = ?
                       WHERE key_code = ?""",
                    (total, errors, new_error_ema, new_avg_dwell,
                     new_dwell_ema, new_avg_flight,
                     daily_p, daily_e, today, now_iso, key_code),
                )
            self._conn.commit()

    def get_key_stats(self, key_code: int | None = None) -> list[dict]:
        """Get stats for one key or all keys."""
        with self._lock:
            if key_code is not None:
                rows = self._conn.execute(
                    "SELECT * FROM key_stats WHERE key_code = ?", (key_code,)
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM key_stats ORDER BY total_presses DESC"
                ).fetchall()
        return [dict(r) for r in rows]

    def get_finger_stats(self) -> dict[str, dict]:
        """Aggregate stats per finger."""
        all_stats = self.get_key_stats()
        fingers: dict[str, dict] = {}
        for s in all_stats:
            f = s["finger"] or "unknown"
            if f not in fingers:
                fingers[f] = {"total_presses": 0, "total_errors": 0,
                              "keys": [], "worst_key": None, "worst_error_rate": 0.0}
            fingers[f]["total_presses"] += s["total_presses"]
            fingers[f]["total_errors"] += s["total_errors"]
            fingers[f]["keys"].append(s)
            if s["error_rate_ema"] > fingers[f]["worst_error_rate"]:
                fingers[f]["worst_error_rate"] = s["error_rate_ema"]
                fingers[f]["worst_key"] = s["key_name"]
        return fingers

    # --- Typo Events (Ring Buffer) ---

    def record_typo(self, error_key: int, intended_key: int | None,
                    correction_ms: int, error_type: str) -> None:
        """Record a typo event. Maintains ring buffer of max TYPO_RING_BUFFER_SIZE."""
        now_iso = datetime.now().isoformat()
        with self._lock:
            self._conn.execute(
                """INSERT INTO typo_events (timestamp, error_key_code, intended_key,
                   correction_ms, error_type) VALUES (?, ?, ?, ?, ?)""",
                (now_iso, error_key, intended_key, correction_ms, error_type),
            )
            # Trim ring buffer
            self._conn.execute(
                """DELETE FROM typo_events WHERE id NOT IN
                   (SELECT id FROM typo_events ORDER BY id DESC LIMIT ?)""",
                (TYPO_RING_BUFFER_SIZE,),
            )
            self._conn.commit()

    def get_typo_events(self, limit: int = 100) -> list[dict]:
        """Get recent typo events."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM typo_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_typo_summary(self) -> dict[str, int]:
        """Count typos by type."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT error_type, COUNT(*) as cnt FROM typo_events GROUP BY error_type"
            ).fetchall()
        return {r["error_type"]: r["cnt"] for r in rows}

    # --- Sessions ---

    def start_session(self, device_name: str) -> int:
        """Start a new daemon session, return session ID."""
        now_iso = datetime.now().isoformat()
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO sessions (started_at, device_name) VALUES (?, ?)",
                (now_iso, device_name),
            )
            self._conn.commit()
            return cursor.lastrowid

    def end_session(self, session_id: int, total_keys: int, total_errors: int) -> None:
        """End a daemon session."""
        now_iso = datetime.now().isoformat()
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET ended_at = ?, total_keys = ?, total_errors = ? WHERE id = ?",
                (now_iso, total_keys, total_errors, session_id),
            )
            self._conn.commit()

    def get_sessions(self, limit: int = 20) -> list[dict]:
        """Get recent sessions."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def session_count(self) -> int:
        """Return total number of completed sessions."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE ended_at IS NOT NULL"
            ).fetchone()
        return row[0]

    # --- Recommendations ---

    def save_recommendations(self, recs: list[dict]) -> None:
        """Save/update actuation recommendations."""
        now_iso = datetime.now().isoformat()
        with self._lock:
            for r in recs:
                self._conn.execute(
                    """INSERT OR REPLACE INTO recommendations
                       (key_code, key_name, current_mm, recommended_mm, reason,
                        confidence, generated_at, applied)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
                    (r["key_code"], r["key_name"], r.get("current_mm", 2.0),
                     r["recommended_mm"], r["reason"], r["confidence"], now_iso),
                )
            self._conn.commit()

    def get_recommendations(self) -> list[dict]:
        """Get all recommendations sorted by confidence."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM recommendations ORDER BY confidence DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Actuation History ---

    def record_actuation_change(
        self,
        key_code: int,
        previous_mm: float,
        new_mm: float,
        source: str = "auto",
        persisted: bool = False,
    ) -> None:
        """Record an actuation change for audit trail."""
        now_iso = datetime.now().isoformat()
        with self._lock:
            self._conn.execute(
                """INSERT INTO actuation_history
                   (timestamp, key_code, previous_mm, new_mm, source, persisted)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (now_iso, key_code, previous_mm, new_mm, source, 1 if persisted else 0),
            )
            self._conn.commit()

    def get_actuation_history(self, limit: int = 50) -> list[dict]:
        """Get recent actuation changes."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM actuation_history ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Utility ---

    def reset(self) -> None:
        """Delete all data."""
        with self._lock:
            self._conn.execute("DELETE FROM key_stats")
            self._conn.execute("DELETE FROM typo_events")
            self._conn.execute("DELETE FROM sessions")
            self._conn.execute("DELETE FROM recommendations")
            self._conn.execute("DELETE FROM actuation_history")
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
