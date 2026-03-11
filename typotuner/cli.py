"""TypoTuner CLI — Click + Rich interface.

Commands: start, stop, status, stats, heatmap, fingers, recommend, reset, web.
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
