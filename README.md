# TypoTuner

![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue) ![License MIT](https://img.shields.io/badge/license-MIT-green) ![Linux only](https://img.shields.io/badge/platform-Linux-lightgrey)

Background typing analysis daemon for Linux. Reads raw keyboard events via evdev, detects typos, tracks per-key error rates with EMA smoothing, and generates actuation point recommendations for the SteelSeries Apex Pro TKL.

## Features

- **evdev-based** — reads kernel input events directly, no X11/Wayland dependency
- **Typo detection** — backspace heuristic classifies errors as adjacent, double, timing, or unknown
- **EMA smoothing** — exponential moving average for error rates and dwell times per key
- **Actuation recommendations** — suggests 0.1–4.0mm actuation points based on your error patterns
- **QWERTZ-native** — correct Y/Z swap handling, single source of truth in `qwertz.py`
- **Privacy-first** — stores only key codes + timing, never characters or words
- **Rich CLI** — ASCII QWERTZ heatmap, finger stats, recommendations
- **Web dashboard** — interactive SVG keyboard, finger comparison, Chart.js visualizations

## How It Works

```
evdev (/dev/input) → async Queue (1000) → Analyzer (EMA + Typo Detection) → SQLite
                                                                              ↓
                                              CLI (Click + Rich)  +  Web Dashboard (:8070)
```

The daemon reads raw key events, buffers them through an async queue to prevent event-loop starvation at high WPM, analyzes timing patterns, and stores per-key statistics with EMA smoothing. No keylogged content — only integer key codes and millisecond timestamps.

## Quick Start

```bash
git clone https://github.com/smlfg/typotuner.git
cd typotuner
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# One-time: add yourself to the input group
sudo usermod -aG input $USER  # requires re-login

# Start the daemon
typotuner start -f  # foreground mode

# View your stats
typotuner stats
typotuner heatmap
typotuner fingers
typotuner recommend

# Web dashboard
typotuner web  # http://localhost:8070
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `typotuner start [-f]` | Start daemon (background or foreground) |
| `typotuner stop` | Stop background daemon |
| `typotuner status` | Show daemon status |
| `typotuner stats` | Per-key statistics table |
| `typotuner heatmap` | ASCII QWERTZ heatmap with color-coded error rates |
| `typotuner fingers` | Per-finger breakdown (left/right hand) |
| `typotuner recommend` | Actuation point recommendations |
| `typotuner reset` | Reset all collected data |
| `typotuner web` | Launch web dashboard on port 8070 |

## Web Dashboard

The web dashboard runs on `http://localhost:8070` with four views:

- **Dashboard** — summary cards, error type breakdown, top error keys
- **Heatmap** — interactive SVG QWERTZ keyboard with toggleable overlays
- **Fingers** — left/right hand comparison, per-finger cards with worst keys
- **Recommendations** — actuation suggestions with confidence bars

Built with FastAPI + htmx + Tailwind CSS + Chart.js.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Input | evdev (Linux kernel events) |
| Processing | asyncio + Queue(maxsize=1000) |
| Analysis | EMA smoothing (α=0.05) |
| Storage | SQLite (thread-safe, file-based) |
| CLI | Click + Rich |
| Web | FastAPI + Jinja2 + htmx + Tailwind + Chart.js |
| Layout | QWERTZ with evdev Y/Z swap handling |

## Tests

```bash
pytest                           # 56 tests
pytest tests/test_qwertz.py      # 14 — finger map, Y/Z swap, neighbors
pytest tests/test_analyzer.py    # 17 — typo detection, counters, timing
pytest tests/test_storage.py     # 13 — CRUD, EMA, sessions, ring buffer
pytest tests/test_recommender.py # 12 — thresholds, confidence, clamping
```

## Privacy

TypoTuner **never** stores what you type. Only integer key codes and timing metrics are recorded. Even if the database leaks, no typed content is recoverable. Typo events are capped at 10,000 entries in a ring buffer.

Database location: `~/.local/share/typotuner/typotuner.db`

## Roadmap

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 (MVP) | Daemon + Analysis + Heatmap + CLI + Web + Recommendations | Done |
| Phase 2 | HID Reverse Engineering (Wireshark + Windows VM) | Blocked: keyboard not arrived |
| Phase 3 | Auto-adjustment via HID SET_REPORT | After Phase 2 |

## License

MIT — see [LICENSE](LICENSE)
