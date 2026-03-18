# SteelSeries Apex Pro TKL 2023 — HID Protocol Notes

## Device
- **VID:PID** = `1038:1628`
- **Interfaces**: Multiple HID interfaces; Interface 1 has Vendor Usage Page `0xFFC0`
- **hidraw**: Typically `/dev/hidraw7` (depends on system)

## Feature Report
- **Interface 1** exposes a 644-byte feature report
- **Report ID**: TBD (likely 0x00)
- **Contains**: Per-key actuation data (among other settings like RGB)

## Actuation Encoding (hypothesis)
- Each key has 1 byte for actuation
- `byte = round((mm - 0.1) / 0.1)` → 0x00 (0.1mm) to 0x27 (4.0mm)
- Default: 2.0mm = 0x13

## RE Steps Completed
- [ ] Read feature report at default settings
- [ ] Change preset via Fn+O/I → read again → diff
- [ ] Identify actuation byte region (offset + length)
- [ ] Verify key position mapping (change single key via SteelSeries GG)
- [ ] Document flash persist command (if different from feature report write)

## Offset Map
| Field | Offset | Length | Notes |
|-------|--------|--------|-------|
| Actuation data | TBD | TBD | Per-key, 1 byte each |

## Key Position Map
TBD — likely USB HID Usage Page 0x07 scancodes as indices.

## Presets (Fn+O/I)
The keyboard has built-in actuation presets. Switching presets via Fn+O/I
changes the actuation values in the feature report (hypothesis to verify).
