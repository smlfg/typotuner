# TypoTuner — FOR_SMLFLG.md

Tipp-Analyse Daemon fuer 10-Finger QWERTZ mit Actuation-Empfehlungen fuer SteelSeries Apex Pro TKL.

---

## Architecture

```
[evdev /dev/input/eventX] → [TypingDaemon asyncio] → [Analyzer EMA+Typo] → [SQLite]
                                    ↑                                          ↓
                             asyncio.Queue(1000)              [CLI Click+Rich] + [Web :8070 FastAPI+htmx]
                          (prevents event-loop starvation)    ASCII-Heatmap      SVG-Keyboard + Finger-Cards
```

---

## File Structure

```
~/Projekte/TypoTuner/
├── typotuner/
│   ├── __init__.py          # version
│   ├── daemon.py            # evdev listener (async queue pattern)
│   ├── storage.py           # SQLite, thread-safe
│   ├── analyzer.py          # EMA, Typo-Detection, Timing
│   ├── qwertz.py            # SINGLE SOURCE OF TRUTH: Finger-Map + Nachbar-Map + Y/Z Swap
│   ├── recommender.py       # Actuation-Empfehlungen
│   └── cli.py               # Click+Rich (stats, heatmap, recommend, start/stop)
├── web/
│   ├── app.py               # FastAPI + Jinja2
│   └── templates/
│       ├── base.html         # Tailwind + htmx + Chart.js
│       ├── dashboard.html    # Uebersicht + Mini-Keyboard
│       ├── heatmap.html      # Interaktive SVG-Keyboard-Heatmap
│       ├── fingers.html      # 10 Finger-Cards + Links/Rechts Vergleich
│       └── recommendations.html
├── services/
│   ├── typotuner.service     # systemd (daemon)
│   └── typotuner-web.service # systemd (dashboard)
├── tests/
│   ├── conftest.py
│   ├── test_qwertz.py
│   ├── test_analyzer.py
│   ├── test_storage.py
│   └── test_recommender.py
├── pyproject.toml
├── .gitignore
└── FOR_SMLFLG.md
```

---

## Tech Decisions

| Technology | Why |
|------------|-----|
| **evdev** | Direct Linux kernel input — no X11/Wayland display server needed, works with `input` group |
| **asyncio + Queue** | Event queue between evdev reader and DB writer prevents event-loop starvation at 150+ WPM |
| **SQLite** | Zero-config, file-based. Stores key_codes + timing. NEVER characters. GDPR-friendly |
| **EMA (Exponential Moving Average)** | Smooths error rates, adapts to recent behavior without storing full history |
| **Click + Rich** | CLI control with pretty output. ASCII heatmap with colored keys |
| **FastAPI + htmx** | Same stack as StudyAgent/FireTracker — proven pattern |

---

## DB Schema (4 tables)

- **key_stats** — Per-key running statistics (EMA error rate, dwell time, flight time)
- **typo_events** — Ring-buffer (max 10.000) of individual typo events
- **sessions** — Daemon session tracking (start/end, total keys/errors)
- **recommendations** — Generated actuation recommendations per key

DB location: `~/.local/share/typotuner/typotuner.db`

---

## Privacy Design

CRITICAL: TypoTuner NEVER stores what you type.
- Only integer key_codes + timing metrics
- No text, no words, no strings
- Even if the DB leaks, no typed content is recoverable
- Typo events: only key_codes + timestamps, max 10.000 in ring-buffer

---

## QWERTZ Y/Z Swap (Critical)

evdev uses US QWERTY key names:
- `KEY_Y` (code 21) = physically **Z** on QWERTZ → right_index
- `KEY_Z` (code 44) = physically **Y** on QWERTZ → left_pinky

`qwertz.py` is the SINGLE SOURCE OF TRUTH for this mapping. All other modules use it.

---

## Typo Detection Algorithm

```
Jeder KEY_DOWN:
  1. Backspace < 500ms seit letzter Taste → vorherige Taste = TYPO
     Typ: "adjacent" (Nachbar-Taste), "double" (Doppel-Druck), "timing" (zu kurz), "unknown"
  2. Sonst: Dwell-Time + Flight-Time berechnen, key_stats updaten

EMA-Update:
  error_rate_ema = 0.01 * is_error + 0.99 * error_rate_ema
  dwell_ema      = 0.02 * dwell_ms + 0.98 * dwell_ema
```

---

## Actuation Recommendation Logic

```
Fehlerrate > 8%  → Actuation ERHOEHEN (zu empfindlich)
Fehlerrate < 2% + langer Dwell → Actuation SENKEN (zu schwer)
Pinky + Fehlerrate > 5% → Sanftere Erhoehung
Clamp: [0.1mm, 4.0mm]
Confidence = min(1.0, total_presses / 500)
Filter: min_sessions >= 3
```

---

## Phase Plan

| Phase | Was | Status |
|-------|-----|--------|
| **Phase 1 (MVP)** | Daemon + Analyse + Heatmap + CLI + Web + Empfehlungen | DONE (MVP) |
| **Phase 2** | HID Reverse Engineering (Wireshark + Windows VM) | Blocked: Keyboard nicht da |
| **Phase 3** | Auto-Adjustment via HID SET_REPORT | Nach Phase 2 |

---

## Setup

```bash
cd ~/Projekte/TypoTuner
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
sudo usermod -aG input $USER  # one-time, requires re-login

# Daemon
typotuner start -f   # foreground

# Stats
typotuner stats
typotuner heatmap
typotuner fingers
typotuner recommend

# Web Dashboard
typotuner web  # http://localhost:8070
```

---

## Lessons Learned

- evdev key codes follow QWERTY names — always remap for QWERTZ in application layer
- `input` group membership required; no root needed after that
- Physical neighbor map must be symmetric — enforced programmatically
- asyncio.Queue between reader and writer prevents event-loop starvation at high WPM
- Y/Z swap: one source of truth (qwertz.py), tested extensively
