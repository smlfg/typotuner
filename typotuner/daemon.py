"""TypoTuner Daemon — evdev keyboard listener with async queue.

Tracks ALL keypresses (not just shortcuts). Never logs characters.
Uses asyncio.Queue between evdev reader and analyzer to prevent
event-loop starvation at high WPM.

Run as user in 'input' group (no root needed).
"""

import asyncio
import os
import signal
import sys
from pathlib import Path

import evdev
from evdev import InputDevice, categorize, ecodes

from .analyzer import Analyzer, KeyEvent
from .storage import Storage


def get_pid_file() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return Path(runtime_dir) / "typotuner.pid"


def write_pid_file() -> None:
    get_pid_file().write_text(str(os.getpid()))


def remove_pid_file() -> None:
    try:
        get_pid_file().unlink()
    except FileNotFoundError:
        pass


def is_running() -> int | None:
    """Check if daemon is running, return PID or None."""
    pid_file = get_pid_file()
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)  # Check if process exists
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        remove_pid_file()
        return None


def find_keyboards() -> list[InputDevice]:
    """Auto-detect keyboard devices by checking for EV_KEY + letter keys."""
    keyboards = []
    for path in evdev.list_devices():
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()
            if ecodes.EV_KEY not in caps:
                continue
            keys = caps[ecodes.EV_KEY]
            if ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
                keyboards.append(dev)
        except (PermissionError, OSError):
            pass
    return keyboards


class TypoTunerDaemon:
    """Main daemon: reads keyboards, feeds analyzer via async queue."""

    def __init__(self, storage: Storage | None = None):
        self._storage = storage or Storage()
        self._analyzer = Analyzer(self._storage)
        self._queue: asyncio.Queue[KeyEvent] = asyncio.Queue(maxsize=1000)
        self._running = True
        self._session_id: int | None = None

    def _handle_shutdown(self, *_):
        print("Shutting down...", file=sys.stderr)
        self._running = False

    async def _read_device(self, device: InputDevice) -> None:
        """Read events from keyboard, enqueue for processing."""
        try:
            async for event in device.async_read_loop():
                if not self._running:
                    break
                if event.type != ecodes.EV_KEY:
                    continue

                key_event = categorize(event)
                code = event.code

                # Only track keys in our finger map + modifiers we care about
                is_down = key_event.keystate == key_event.key_down
                is_up = key_event.keystate == key_event.key_up

                if not (is_down or is_up):
                    continue  # skip key_hold repeats

                timestamp_ns = event.timestamp() * 1_000_000_000
                ke = KeyEvent(
                    key_code=code,
                    timestamp_ns=int(timestamp_ns),
                    is_down=is_down,
                )

                try:
                    self._queue.put_nowait(ke)
                except asyncio.QueueFull:
                    pass  # Drop event rather than block reader

        except (OSError, asyncio.CancelledError):
            pass

    async def _process_events(self) -> None:
        """Consume events from queue, run through analyzer."""
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                self._analyzer.process_event(event)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def run(self, foreground: bool = False) -> None:
        """Main entry point."""
        keyboards = find_keyboards()
        if not keyboards:
            print(
                "No keyboard devices found. Are you in the 'input' group?",
                file=sys.stderr,
            )
            sys.exit(1)

        device_names = ", ".join(kb.name for kb in keyboards)
        print(f"Monitoring {len(keyboards)} keyboard(s):", file=sys.stderr)
        for kb in keyboards:
            print(f"  {kb.path} — {kb.name}", file=sys.stderr)

        self._session_id = self._storage.start_session(device_names)
        write_pid_file()

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGTERM, self._handle_shutdown)
        loop.add_signal_handler(signal.SIGINT, self._handle_shutdown)

        # Launch reader tasks + processor
        tasks = [
            asyncio.create_task(self._read_device(dev))
            for dev in keyboards
        ]
        tasks.append(asyncio.create_task(self._process_events()))

        try:
            await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                t.cancel()
            if self._session_id is not None:
                state = self._analyzer.state
                self._storage.end_session(
                    self._session_id, state.total_keys, state.total_errors
                )
            remove_pid_file()
            self._storage.close()


def main():
    daemon = TypoTunerDaemon()
    asyncio.run(daemon.run(foreground=True))


if __name__ == "__main__":
    main()
