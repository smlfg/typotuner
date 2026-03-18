"""TypoTuner CLI — Click + Rich interface.

Commands: start, stop, status, stats, heatmap, fingers, recommend, reset, web,
          device, apply, restore, factory-reset, probe.
"""

import os
import signal
import subprocess
import sys

import click
from rich.console import Console
from rich.table import Table
from rich import box

from .daemon import is_running, get_pid_file, TypoTunerDaemon
from .storage import Storage
from .recommender import generate_recommendations
from . import qwertz

console = Console()


def _color_for_error_rate(rate: float) -> str:
    """Return Rich color based on error rate."""
    if rate < 0.02:
        return "green"
    elif rate < 0.05:
        return "yellow"
    elif rate < 0.08:
        return "dark_orange"
    else:
        return "red"


@click.group()
def cli():
    """TypoTuner — Typing analysis for 10-finger QWERTZ optimization."""
    pass


@cli.command()
@click.option("-f", "--foreground", is_flag=True, help="Run in foreground (don't daemonize)")
def start(foreground: bool):
    """Start the typing analysis daemon."""
    pid = is_running()
    if pid:
        console.print(f"[yellow]Daemon already running (PID {pid})[/yellow]")
        return

    if foreground:
        console.print("[green]Starting TypoTuner daemon (foreground)...[/green]")
        import asyncio
        daemon = TypoTunerDaemon()
        asyncio.run(daemon.run(foreground=True))
    else:
        console.print("[green]Starting TypoTuner daemon...[/green]")
        subprocess.Popen(
            [sys.executable, "-m", "typotuner.daemon"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        console.print("[green]Daemon started in background.[/green]")


@cli.command()
def stop():
    """Stop the typing analysis daemon."""
    pid = is_running()
    if not pid:
        console.print("[yellow]Daemon is not running.[/yellow]")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        console.print(f"[green]Daemon stopped (PID {pid}).[/green]")
    except ProcessLookupError:
        console.print("[yellow]Daemon process not found, cleaning up PID file.[/yellow]")
        get_pid_file().unlink(missing_ok=True)


@cli.command()
def status():
    """Check if the daemon is running."""
    pid = is_running()
    if pid:
        console.print(f"[green]Daemon running (PID {pid})[/green]")
    else:
        console.print("[dim]Daemon is not running.[/dim]")


@cli.command()
@click.option("-n", "--limit", default=30, help="Number of keys to show")
def stats(limit: int):
    """Show per-key typing statistics."""
    with Storage() as db:
        all_stats = db.get_key_stats()

    if not all_stats:
        console.print("[dim]No data yet. Start the daemon and type![/dim]")
        return

    table = Table(title="Key Statistics", box=box.ROUNDED)
    table.add_column("Key", style="bold")
    table.add_column("Finger", style="cyan")
    table.add_column("Presses", justify="right")
    table.add_column("Errors", justify="right")
    table.add_column("Error %", justify="right")
    table.add_column("EMA %", justify="right")
    table.add_column("Dwell ms", justify="right")
    table.add_column("Flight ms", justify="right")

    for s in all_stats[:limit]:
        error_pct = (s["total_errors"] / s["total_presses"] * 100) if s["total_presses"] > 0 else 0
        ema_pct = s["error_rate_ema"] * 100
        color = _color_for_error_rate(s["error_rate_ema"])

        table.add_row(
            s["key_name"],
            s["finger"] or "?",
            str(s["total_presses"]),
            f"[{color}]{s['total_errors']}[/{color}]",
            f"[{color}]{error_pct:.1f}%[/{color}]",
            f"[{color}]{ema_pct:.1f}%[/{color}]",
            f"{s['dwell_ema']:.0f}" if s["dwell_ema"] else "-",
            f"{s['avg_flight_ms']:.0f}" if s["avg_flight_ms"] else "-",
        )

    console.print(table)
    console.print(f"\n[dim]Showing {min(limit, len(all_stats))}/{len(all_stats)} keys[/dim]")


@cli.command()
def heatmap():
    """Show ASCII keyboard heatmap colored by error rate."""
    with Storage() as db:
        all_stats = db.get_key_stats()

    if not all_stats:
        console.print("[dim]No data yet. Start the daemon and type![/dim]")
        return

    # Build lookup: key_code -> error_rate_ema
    rates = {s["key_code"]: s["error_rate_ema"] for s in all_stats}

    def _fmt(key_code: int, label: str, width: int = 3) -> str:
        rate = rates.get(key_code, 0.0)
        color = _color_for_error_rate(rate)
        padded = label.center(width)
        return f"[{color}][{padded}][/{color}]"

    console.print("\n[bold]Error Rate Heatmap (EMA)[/bold]\n")

    # Number row
    row1 = " ".join([
        _fmt(41, "^"), _fmt(2, "1"), _fmt(3, "2"), _fmt(4, "3"),
        _fmt(5, "4"), _fmt(6, "5"), _fmt(7, "6"), _fmt(8, "7"),
        _fmt(9, "8"), _fmt(10, "9"), _fmt(11, "0"), _fmt(12, "ß"),
        _fmt(13, "´"),
    ])
    console.print(f"  {row1}")

    # Top row (QWERTZ)
    row2 = " ".join([
        _fmt(16, "Q"), _fmt(17, "W"), _fmt(18, "E"), _fmt(19, "R"),
        _fmt(20, "T"), _fmt(21, "Z"), _fmt(22, "U"), _fmt(23, "I"),
        _fmt(24, "O"), _fmt(25, "P"), _fmt(26, "Ü"), _fmt(27, "+"),
    ])
    console.print(f"    {row2}")

    # Home row
    row3 = " ".join([
        _fmt(30, "A"), _fmt(31, "S"), _fmt(32, "D"), _fmt(33, "F"),
        _fmt(34, "G"), _fmt(35, "H"), _fmt(36, "J"), _fmt(37, "K"),
        _fmt(38, "L"), _fmt(39, "Ö"), _fmt(40, "Ä"), _fmt(43, "#"),
    ])
    console.print(f"     {row3}")

    # Bottom row
    row4 = " ".join([
        _fmt(86, "<"), _fmt(44, "Y"), _fmt(45, "X"), _fmt(46, "C"),
        _fmt(47, "V"), _fmt(48, "B"), _fmt(49, "N"), _fmt(50, "M"),
        _fmt(51, ","), _fmt(52, "."), _fmt(53, "-"),
    ])
    console.print(f"   {row4}")

    console.print("\n  [green]<2%[/green]  [yellow]2-5%[/yellow]  [dark_orange]5-8%[/dark_orange]  [red]>8%[/red]\n")


@cli.command()
def fingers():
    """Show per-finger typing analysis."""
    with Storage() as db:
        finger_stats = db.get_finger_stats()

    if not finger_stats:
        console.print("[dim]No data yet. Start the daemon and type![/dim]")
        return

    table = Table(title="Finger Analysis", box=box.ROUNDED)
    table.add_column("Finger", style="bold")
    table.add_column("Presses", justify="right")
    table.add_column("Errors", justify="right")
    table.add_column("Error %", justify="right")
    table.add_column("Worst Key", style="red")

    for finger in qwertz.FINGER_NAMES:
        fs = finger_stats.get(finger)
        if not fs:
            continue
        total = fs["total_presses"]
        errors = fs["total_errors"]
        rate = errors / total if total > 0 else 0
        color = _color_for_error_rate(rate)
        worst = fs["worst_key"] or "-"

        display = finger.replace("_", " ").title()
        table.add_row(
            display,
            str(total),
            f"[{color}]{errors}[/{color}]",
            f"[{color}]{rate:.1%}[/{color}]",
            worst,
        )

    console.print(table)

    # Left vs Right comparison
    left_p = sum(f["total_presses"] for n, f in finger_stats.items() if n.startswith("left"))
    right_p = sum(f["total_presses"] for n, f in finger_stats.items() if n.startswith("right"))
    left_e = sum(f["total_errors"] for n, f in finger_stats.items() if n.startswith("left"))
    right_e = sum(f["total_errors"] for n, f in finger_stats.items() if n.startswith("right"))

    console.print(f"\n[bold]Left hand:[/bold]  {left_p} presses, {left_e} errors ({left_e/left_p:.1%} error rate)" if left_p else "")
    console.print(f"[bold]Right hand:[/bold] {right_p} presses, {right_e} errors ({right_e/right_p:.1%} error rate)" if right_p else "")


@cli.command()
def recommend():
    """Show actuation recommendations for SteelSeries Apex Pro."""
    with Storage() as db:
        recs = generate_recommendations(db)

    if not recs:
        console.print("[dim]Not enough data for recommendations yet.[/dim]")
        console.print("[dim]Need at least 3 completed sessions and significant typing data.[/dim]")
        return

    table = Table(title="Actuation Recommendations — SteelSeries Apex Pro TKL", box=box.ROUNDED)
    table.add_column("Key", style="bold")
    table.add_column("Current", justify="right")
    table.add_column("→", justify="center")
    table.add_column("Recommended", justify="right", style="cyan")
    table.add_column("Confidence", justify="right")
    table.add_column("Reason")

    for r in recs:
        direction = "↑" if r["recommended_mm"] > r["current_mm"] else "↓"
        conf_pct = f"{r['confidence']:.0%}"
        table.add_row(
            r["key_name"],
            f"{r['current_mm']:.1f}mm",
            direction,
            f"{r['recommended_mm']:.1f}mm",
            conf_pct,
            r["reason"],
        )

    console.print(table)
    console.print("\n[dim]↑ = increase actuation (less sensitive)  ↓ = decrease (more sensitive)[/dim]")


@cli.command()
@click.confirmation_option(prompt="Delete ALL typing data?")
def reset():
    """Reset all collected typing data."""
    with Storage() as db:
        db.reset()
    console.print("[green]All data cleared.[/green]")


@cli.command()
@click.option("-p", "--port", default=8070, help="Port for web dashboard")
def web(port: int):
    """Start the web dashboard."""
    console.print(f"[green]Starting web dashboard on http://localhost:{port}[/green]")
    import uvicorn
    uvicorn.run("typotuner.web.app:app", host="0.0.0.0", port=port, reload=False)


# ---------------------------------------------------------------------------
# Phase 2: HID Actuation Control Commands
# ---------------------------------------------------------------------------


@cli.command("device")
def device_info():
    """Show connected SteelSeries keyboard info and current actuation."""
    from .hid import device, protocol
    from .hid.actuation import ActuationController

    try:
        path = device.find_device()
    except device.DeviceNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return

    info = device.get_device_info(path)
    console.print(f"\n[bold]Device:[/bold] {info['name']}")
    console.print(f"[bold]Path:[/bold]   {info['hidraw_path']}")
    console.print(f"[bold]VID:PID:[/bold] {info['vendor_id']:04x}:{info['product_id']:04x}")

    try:
        with ActuationController() as ctrl:
            actuation = ctrl.read_current_actuation()
            if actuation is None:
                console.print(
                    "\n[yellow]Actuation map not readable — "
                    "protocol offsets not yet determined (RE needed).[/yellow]"
                )
            else:
                console.print(f"\n[bold]Per-key actuation ({len(actuation)} keys):[/bold]")
                from .hid import keymap
                table = Table(box=box.ROUNDED)
                table.add_column("Key", style="bold")
                table.add_column("Actuation", justify="right", style="cyan")
                for ss_pos, mm in sorted(actuation.items()):
                    evdev_code = keymap.ss_to_evdev(ss_pos)
                    label = keymap.evdev_to_label(evdev_code) if evdev_code else f"SS_{ss_pos}"
                    table.add_row(label, f"{mm:.1f}mm")
                console.print(table)
    except device.DevicePermissionError as e:
        console.print(f"\n[red]{e}[/red]")
    except OSError as e:
        console.print(f"\n[yellow]Could not read device: {e}[/yellow]")


@cli.command("probe")
@click.option("--save", type=click.Path(), help="Save raw report to file")
def probe(save: str | None):
    """Read raw feature report for reverse engineering."""
    from .hid import device, protocol
    from .hid.actuation import ActuationController

    try:
        with ActuationController() as ctrl:
            report = ctrl.read_raw_report()
    except (device.DeviceNotFoundError, device.DevicePermissionError, OSError) as e:
        console.print(f"[red]{e}[/red]")
        return

    console.print(f"\n[bold]Feature Report:[/bold] {len(report)} bytes")

    # Show hex dump (first 128 bytes + last 32)
    console.print("\n[dim]First 128 bytes:[/dim]")
    for i in range(0, min(128, len(report)), 16):
        hex_part = " ".join(f"{b:02X}" for b in report[i : i + 16])
        ascii_part = "".join(
            chr(b) if 32 <= b < 127 else "." for b in report[i : i + 16]
        )
        console.print(f"  {i:04X}: {hex_part:<48s}  {ascii_part}")

    if len(report) > 128:
        console.print(f"\n[dim]... ({len(report) - 160} bytes omitted) ...[/dim]")
        start = len(report) - 32
        console.print(f"\n[dim]Last 32 bytes:[/dim]")
        for i in range(start, len(report), 16):
            hex_part = " ".join(f"{b:02X}" for b in report[i : i + 16])
            ascii_part = "".join(
                chr(b) if 32 <= b < 127 else "." for b in report[i : i + 16]
            )
            console.print(f"  {i:04X}: {hex_part:<48s}  {ascii_part}")

    # Non-zero byte analysis
    non_zero = [(i, b) for i, b in enumerate(report) if b != 0]
    console.print(f"\n[bold]Non-zero bytes:[/bold] {len(non_zero)} / {len(report)}")

    # Check for potential actuation region (bytes in 0x00-0x27 range)
    potential = [(i, b) for i, b in enumerate(report) if 0x00 <= b <= 0x27 and b != 0]
    console.print(f"[bold]Bytes in actuation range (0x01-0x27):[/bold] {len(potential)}")

    if save:
        from pathlib import Path
        Path(save).write_bytes(report)
        console.print(f"\n[green]Report saved to {save}[/green]")

    console.print(
        "\n[dim]Tip: Change actuation preset (Fn+O/I), then run 'probe' again "
        "and compare to find actuation bytes.[/dim]"
    )


@cli.command("diff-reports")
@click.argument("file_a", type=click.Path(exists=True))
@click.argument("file_b", type=click.Path(exists=True))
def diff_reports(file_a: str, file_b: str):
    """Diff two saved feature reports (for reverse engineering)."""
    from pathlib import Path
    from .hid import protocol

    a = Path(file_a).read_bytes()
    b = Path(file_b).read_bytes()
    diffs = protocol.diff_reports(a, b)
    console.print(protocol.format_diff(diffs))


@cli.command("apply")
@click.option("--dry-run", is_flag=True, default=True, help="Show changes without applying (default)")
@click.option("--apply", "do_apply", is_flag=True, help="Actually send to keyboard (RAM only)")
@click.option("--persist", is_flag=True, help="Persist to keyboard flash (permanent)")
def apply_actuation(dry_run: bool, do_apply: bool, persist: bool):
    """Apply actuation recommendations to the keyboard."""
    from .hid import device, protocol
    from .hid.actuation import ActuationController

    with Storage() as db:
        recs = generate_recommendations(db)

    if not recs:
        console.print("[dim]No recommendations available. Need more typing data.[/dim]")
        return

    if not do_apply:
        # Dry run (default)
        console.print("\n[bold]Planned actuation changes (dry-run):[/bold]\n")
        table = Table(box=box.ROUNDED)
        table.add_column("Key", style="bold")
        table.add_column("Current", justify="right")
        table.add_column("→")
        table.add_column("New", justify="right", style="cyan")
        table.add_column("Confidence", justify="right")
        table.add_column("Reason")

        for r in recs:
            direction = "↑" if r["recommended_mm"] > r["current_mm"] else "↓"
            table.add_row(
                r["key_name"],
                f"{r['current_mm']:.1f}mm",
                direction,
                f"{r['recommended_mm']:.1f}mm",
                f"{r['confidence']:.0%}",
                r["reason"],
            )

        console.print(table)
        console.print("\n[dim]Use --apply to send to keyboard (RAM only).[/dim]")
        console.print("[dim]Use --apply --persist to also save to flash.[/dim]")
        return

    # Actually apply
    try:
        with Storage() as db, ActuationController(storage=db) as ctrl:
            backup_path, applied = ctrl.apply_recommendations(recs, persist=persist)
    except (device.DeviceNotFoundError, device.DevicePermissionError) as e:
        console.print(f"[red]{e}[/red]")
        return
    except protocol.ProtocolError as e:
        console.print(f"[red]Protocol error: {e}[/red]")
        return
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return

    mode = "RAM + Flash" if persist else "RAM only"
    console.print(f"\n[green]Applied {len(applied)} changes ({mode}).[/green]")
    console.print(f"[dim]Backup: {backup_path}[/dim]")

    for c in applied:
        console.print(f"  {c['key_name']}: {c['previous_mm']:.1f}mm → {c['new_mm']:.1f}mm")


@cli.command("restore")
@click.argument("file", required=False, type=click.Path(exists=True))
def restore(file: str | None):
    """Restore actuation from a backup file (or latest backup)."""
    from .hid import device
    from .hid.actuation import ActuationController
    from .hid import safety
    from pathlib import Path

    try:
        with ActuationController() as ctrl:
            backup_path = Path(file) if file else None
            restored = ctrl.restore(backup_path)
    except FileNotFoundError:
        console.print("[red]No backups found.[/red]")
        return
    except (device.DeviceNotFoundError, device.DevicePermissionError) as e:
        console.print(f"[red]{e}[/red]")
        return
    except safety.SafetyError as e:
        console.print(f"[red]{e}[/red]")
        return

    console.print(f"[green]Restored from: {restored}[/green]")


@cli.command("factory-reset")
@click.confirmation_option(prompt="Reset ALL keys to 2.0mm default actuation?")
@click.option("--persist", is_flag=True, help="Also persist to flash")
def factory_reset(persist: bool):
    """Reset all keys to default actuation (2.0mm)."""
    from .hid import device
    from .hid.actuation import ActuationController
    from .hid import safety

    try:
        with ActuationController() as ctrl:
            backup = ctrl.factory_reset(persist=persist)
    except (device.DeviceNotFoundError, device.DevicePermissionError) as e:
        console.print(f"[red]{e}[/red]")
        return
    except safety.SafetyError as e:
        console.print(f"[red]{e}[/red]")
        return

    mode = "RAM + Flash" if persist else "RAM only"
    console.print(f"[green]All keys reset to 2.0mm ({mode}).[/green]")
    console.print(f"[dim]Backup: {backup}[/dim]")
