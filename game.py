"""
Tempo Poker — LLM players compete for real USDC.
LLM calls are paid automatically via your local Tempo wallet.

When more than max_per_table players are configured, they're split into
parallel tables of up to 8 each.

Usage:
  python game.py                  # uses config.yaml
  python game.py --config my.yaml
  python game.py --hands 10
  python game.py --verbose        # show LLM debug logs
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
import threading
import time
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

import payments
import state as game_state
from player import Player
from table import MAX_PLAYERS, PokerTable

console = Console()
_console_lock = threading.Lock()


# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------

def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def build_players(cfg: dict) -> list[Player]:
    buy_in = float(cfg["table"]["buy_in"])
    return [
        Player(name=p["name"], model=p["model"], stack=buy_in)
        for p in cfg["players"]
    ]


def split_into_tables(players: list[Player], max_per_table: int = MAX_PLAYERS) -> list[list[Player]]:
    """
    Distribute players across tables of at most max_per_table.
    Tries to keep table sizes as equal as possible.

    e.g. 13 players → two tables of 7 and 6 (not 8 and 5).
    """
    n = len(players)
    if n <= max_per_table:
        return [players]

    num_tables = math.ceil(n / max_per_table)
    base_size = n // num_tables
    extras = n % num_tables

    tables = []
    idx = 0
    for i in range(num_tables):
        size = base_size + (1 if i < extras else 0)
        tables.append(players[idx : idx + size])
        idx += size

    return tables


# ------------------------------------------------------------------
# Display
# ------------------------------------------------------------------

def print_standings(players: list[Player], hand_num: int, buy_in: float, table_name: str = "") -> None:
    title = f"Standings after hand #{hand_num}" + (f" — {table_name}" if table_name else "")
    t = Table(title=title, box=box.ROUNDED, header_style="bold magenta")
    t.add_column("Rank", justify="center")
    t.add_column("Player")
    t.add_column("Model", style="dim")
    t.add_column("Stack", justify="right")
    t.add_column("Net P&L", justify="right")
    t.add_column("Hands", justify="right")

    for i, p in enumerate(sorted(players, key=lambda p: p.stack, reverse=True), 1):
        net = p.stack - buy_in
        net_str = f"[green]+${net:.2f}[/]" if net >= 0 else f"[red]-${abs(net):.2f}[/]"
        t.add_row(str(i), p.name, p.model.split("/")[-1], f"${p.stack:.2f}", net_str, str(p.hands_played))

    with _console_lock:
        console.print(t)


def print_final_results(all_players: list[Player], buy_in: float) -> None:
    t = Table(
        title="[bold]Final Results — All Tables[/]",
        box=box.HEAVY,
        header_style="bold white on blue",
    )
    t.add_column("Rank", justify="center")
    t.add_column("Player")
    t.add_column("Model", style="dim")
    t.add_column("Final Stack", justify="right")
    t.add_column("Net P&L", justify="right")
    t.add_column("Hands", justify="right")

    for i, p in enumerate(sorted(all_players, key=lambda p: p.stack, reverse=True), 1):
        net = p.stack - buy_in
        net_str = f"[green]+${net:.2f}[/]" if net >= 0 else f"[red]-${abs(net):.2f}[/]"
        rank_str = "[bold yellow]1[/]" if i == 1 else str(i)
        t.add_row(rank_str, p.name, p.model.split("/")[-1], f"${p.stack:.2f}", net_str, str(p.hands_played))

    console.print(Panel(t, border_style="gold1"))


# ------------------------------------------------------------------
# Table runner
# ------------------------------------------------------------------

def run_table(
    table_name: str,
    players: list[Player],
    big_blind: float,
    small_blind: float,
    max_hands: int,
    buy_in: float,
    standings_every: int,
) -> None:
    table = PokerTable(players, big_blind=big_blind, small_blind=small_blind)

    with _console_lock:
        console.print(Panel(
            f"{len(players)} players  ·  "
            f"Blinds ${small_blind:.2f}/${big_blind:.2f}  ·  "
            f"Buy-in ${buy_in:.2f} USDC  ·  Max {max_hands} hands",
            title=f"[bold yellow]♠  {table_name}  ♠[/]",
            border_style="blue",
        ))

    for hand_num in range(1, max_hands + 1):
        solvent = [p for p in players if p.stack > 0]
        if len(solvent) < 2:
            with _console_lock:
                console.print(
                    f"\n[bold green]{solvent[0].name}[/] is the last player standing "
                    f"at {table_name}!"
                )
            break

        try:
            table.play_hand()
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            with _console_lock:
                console.print(f"\n[red]{table_name} — error in hand #{hand_num}: {exc}[/]")
            logging.getLogger(__name__).exception("Hand error")
            time.sleep(1)
            continue

        if hand_num % standings_every == 0:
            print_standings(players, hand_num, buy_in, table_name)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Tempo Poker — LLM agents, real USDC")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--hands", type=int, default=None)
    parser.add_argument("--ui", action="store_true", help="Start spectator web UI on port 8080")
    parser.add_argument("--port", type=int, default=8080, help="UI server port (default 8080)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(name)s: %(message)s",
    )

    config_path = Path(args.config)
    if not config_path.exists():
        console.print(f"[red]Config not found: {config_path}[/]")
        sys.exit(1)

    cfg = load_config(str(config_path))
    table_cfg = cfg["table"]
    buy_in = float(table_cfg["buy_in"])
    big_blind = float(table_cfg["big_blind"])
    small_blind = float(table_cfg["small_blind"])
    max_hands = args.hands or int(table_cfg.get("max_hands", 50))
    standings_every = int(table_cfg.get("standings_every", 5))
    max_per_table = int(table_cfg.get("max_per_table", MAX_PLAYERS))

    if max_per_table > MAX_PLAYERS:
        console.print(f"[red]max_per_table cannot exceed {MAX_PLAYERS}.[/]")
        sys.exit(1)

    all_players = build_players(cfg)
    tables = split_into_tables(all_players, max_per_table)

    # Start spectator UI server in background thread
    if args.ui:
        import threading
        import server as ui_server
        t = threading.Thread(target=ui_server.run, kwargs={"port": args.port}, daemon=True)
        t.start()
        console.print(f"[green]Spectator UI →[/] http://localhost:{args.port}  [dim](share this URL)[/]")

    game_state.emit_waiting()

    # Check wallet
    errors = payments.check_tempo_ready()
    if errors:
        for e in errors:
            console.print(f"[red]✗ {e}[/]")
        sys.exit(1)

    payments.print_wallet_summary()

    console.print(Panel(
        f"[bold]Tempo Poker[/]  ·  {len(all_players)} players  ·  "
        f"{len(tables)} table{'s' if len(tables) > 1 else ''}  ·  "
        f"Max {max_per_table} per table\n"
        f"[dim]10-second turn limit  ·  LLM costs via Tempo wallet[/]",
        border_style="gold1",
        title="[bold yellow]♠ ♥ ♦ ♣  Tempo Poker  ♣ ♦ ♥ ♠[/]",
    ))

    if len(tables) == 1:
        # Single table — run directly
        try:
            run_table(
                table_name="Table 1",
                players=tables[0],
                big_blind=big_blind,
                small_blind=small_blind,
                max_hands=max_hands,
                buy_in=buy_in,
                standings_every=standings_every,
            )
        except KeyboardInterrupt:
            console.print("\n[yellow]Game interrupted.[/]")
    else:
        # Multiple tables — run in parallel threads
        threads = []
        for i, table_players in enumerate(tables, 1):
            t = threading.Thread(
                target=run_table,
                name=f"Table-{i}",
                kwargs=dict(
                    table_name=f"Table {i}",
                    players=table_players,
                    big_blind=big_blind,
                    small_blind=small_blind,
                    max_hands=max_hands,
                    buy_in=buy_in,
                    standings_every=standings_every,
                ),
                daemon=True,
            )
            threads.append(t)

        for t in threads:
            t.start()

        try:
            for t in threads:
                t.join()
        except KeyboardInterrupt:
            console.print("\n[yellow]Game interrupted.[/]")

    print_final_results(all_players, buy_in)


if __name__ == "__main__":
    main()
