"""
Poker table: orchestrates a full hand of Texas Hold'em for up to 8 players.
Handles blinds, all four streets, side pots, and showdown.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

import engine
import state as game_state
from engine import Pot, calculate_pots, distribute_pots, draw, new_deck
from player import Player

logger = logging.getLogger(__name__)
console = Console()

MAX_PLAYERS = 8


@dataclass
class HandResult:
    hand_num: int
    winners: list[str]
    pot: float
    reason: str        # "showdown" | "fold"
    board: list[int]
    action_log: list[str]


class PokerTable:

    def __init__(
        self,
        players: list[Player],
        big_blind: float = 0.10,
        small_blind: float = 0.05,
    ) -> None:
        if len(players) > MAX_PLAYERS:
            raise ValueError(f"Max {MAX_PLAYERS} players, got {len(players)}")
        if len(players) < 2:
            raise ValueError("Need at least 2 players")

        self.players = players
        self.big_blind = big_blind
        self.small_blind = small_blind
        self.dealer_idx = 0
        self.hand_num = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def play_hand(self) -> HandResult:
        self.hand_num += 1
        active = [p for p in self.players if p.stack > 0]

        if len(active) < 2:
            survivor = active[0] if active else self.players[0]
            return HandResult(
                hand_num=self.hand_num,
                winners=[survivor.name],
                pot=0,
                reason="no_opponents",
                board=[],
                action_log=[],
            )

        for p in active:
            p.reset_for_hand()

        deck = new_deck()

        # Deal hole cards
        for p in active:
            p.hole_cards = draw(deck, 2)

        _print_hand_header(self.hand_num, active, self.dealer_idx)

        # Blinds
        n = len(active)
        sb_idx = (self.dealer_idx + 1) % n
        bb_idx = (self.dealer_idx + 2) % n

        sb = active[sb_idx]
        bb = active[bb_idx]

        sb_post = min(self.small_blind, sb.stack)
        bb_post = min(self.big_blind, bb.stack)

        sb.stack -= sb_post
        sb.bet = sb_post
        bb.stack -= bb_post
        bb.bet = bb_post

        # contributions[player] = total chips put in this hand
        contributions: dict[Player, float] = {p: 0.0 for p in active}
        contributions[sb] += sb_post
        contributions[bb] += bb_post
        pot = sb_post + bb_post

        console.print(
            f"  Blinds: [cyan]{sb.name}[/] posts ${sb_post:.2f} (SB)  "
            f"[cyan]{bb.name}[/] posts ${bb_post:.2f} (BB)  "
            f"Pot: [yellow]${pot:.2f}[/]"
        )
        self._dealer_idx_snapshot = self.dealer_idx % n
        game_state.emit_hand_start(
            self.hand_num, active, self._dealer_idx_snapshot, pot, sb.name, bb.name
        )

        board: list[int] = []
        action_log: list[str] = []

        # Streets: (name, cards_to_deal, first_actor_offset_from_dealer)
        # Preflop: first actor is after BB (offset +3 from dealer)
        # Postflop: first actor is SB (offset +1 from dealer, skipping dealer)
        streets = [
            ("preflop", 0, (self.dealer_idx + 3) % n, self.big_blind),
            ("flop",    3, (self.dealer_idx + 1) % n, 0.0),
            ("turn",    1, (self.dealer_idx + 1) % n, 0.0),
            ("river",   1, (self.dealer_idx + 1) % n, 0.0),
        ]

        for street_name, num_cards, first_idx, opening_bet in streets:
            if num_cards:
                board.extend(draw(deck, num_cards))

            # Reset per-street bets (except preflop where blinds already set them)
            if street_name != "preflop":
                for p in active:
                    if not p.folded:
                        p.bet = 0.0

            in_hand = [p for p in active if not p.folded]
            if len(in_hand) <= 1:
                break

            # Skip street if everyone is all-in
            can_bet = [p for p in in_hand if not p.all_in and p.stack > 0]
            if len(can_bet) <= 1:
                _print_street(street_name, board, pot)
                continue

            _print_street(street_name, board, pot)
            game_state.emit_street(
                self.hand_num, street_name, board, pot, active, self.dealer_idx % n
            )

            pot, street_log = self._betting_round(
                active=active,
                pot=pot,
                contributions=contributions,
                current_bet=opening_bet,
                first_idx=first_idx,
                street=street_name,
                board=board,
            )
            action_log.extend(street_log)

            in_hand = [p for p in active if not p.folded]
            if len(in_hand) == 1:
                winner = in_hand[0]
                winner.stack += pot
                winner.total_won += pot
                winner.hands_played += 1
                console.print(
                    f"\n  [bold green]{winner.name}[/] wins [yellow]${pot:.2f}[/] "
                    f"(all others folded)"
                )
                game_state.emit_fold_win(
                    self.hand_num, street_name, board, pot, active, self.dealer_idx % n, winner
                )
                self.dealer_idx = (self.dealer_idx + 1) % n
                return HandResult(
                    hand_num=self.hand_num,
                    winners=[winner.name],
                    pot=pot,
                    reason="fold",
                    board=board,
                    action_log=action_log,
                )

        # Showdown
        in_hand = [p for p in active if not p.folded]
        _print_showdown(in_hand, board)

        pots = calculate_pots(contributions)
        winnings = distribute_pots(pots, board)

        winner_names = []
        hand_descs = {}
        for p in in_hand:
            hand_descs[p.name] = engine.rank_description(engine.evaluate(p.hole_cards, board))
        for p, amount in winnings.items():
            p.stack += amount
            p.total_won += amount
            winner_names.append(p.name)
            console.print(
                f"  [bold green]{p.name}[/] wins [yellow]${amount:.2f}[/]  "
                f"({hand_descs.get(p.name, '')})"
            )

        game_state.emit_showdown(
            self.hand_num, board, pot, active, self.dealer_idx % n, winnings, hand_descs
        )

        for p in active:
            p.hands_played += 1

        self.dealer_idx = (self.dealer_idx + 1) % n

        return HandResult(
            hand_num=self.hand_num,
            winners=winner_names,
            pot=pot,
            reason="showdown",
            board=board,
            action_log=action_log,
        )

    # ------------------------------------------------------------------
    # Betting round
    # ------------------------------------------------------------------

    def _betting_round(
        self,
        active: list[Player],
        pot: float,
        contributions: dict[Player, float],
        current_bet: float,
        first_idx: int,
        street: str,
        board: list[int],
    ) -> tuple[float, list[str]]:
        """
        Run one betting round. Returns (new_pot, action_log).
        Mutates player stacks/bets and contributions in-place.
        """
        n = len(active)
        min_raise_increment = self.big_blind
        acted: set[str] = set()   # names who've acted since last raise
        action_log: list[str] = []

        # Safety cap: no hand should need more than n*4 actions
        max_actions = n * 6
        actions_taken = 0
        idx = first_idx % n

        while actions_taken < max_actions:
            # Players who can still act this round
            eligible = [
                p for p in active
                if not p.folded and not p.all_in and p.stack > 0
            ]
            if not eligible:
                break

            # Round over when everyone eligible has acted and matched current_bet
            if (
                all(p.name in acted for p in eligible)
                and all(p.bet >= current_bet for p in eligible)
            ):
                break

            player = active[idx % n]
            idx += 1

            if player.folded or player.all_in or player.stack <= 0:
                continue

            to_call = max(0.0, current_bet - player.bet)

            # Skip if already matched and acted
            if player.name in acted and to_call <= 0:
                continue

            gs = {
                "street": street,
                "community_cards": board,
                "pot": pot,
                "to_call": round(to_call, 6),
                "min_raise": round(current_bet + min_raise_increment, 6),
                "current_bet": round(current_bet, 6),
                "big_blind": self.big_blind,
                "recent_actions": action_log[-5:],
                "position": self._position_label(player, active),
                "num_active": len(eligible),
                "other_players": [
                    {
                        "name": p.name,
                        "stack": round(p.stack, 6),
                        "folded": p.folded,
                        "bet": round(p.bet, 6),
                        "all_in": p.all_in,
                    }
                    for p in active
                    if p.name != player.name
                ],
            }

            game_state.emit_thinking(
                self.hand_num, street, board,
                sum(contributions.values()), active, self._dealer_idx_snapshot, player
            )
            result = player.decide(gs)
            action = result["action"]
            amount = float(result.get("amount", 0.0))

            log_entry = self._apply_action(
                player=player,
                action=action,
                amount=amount,
                to_call=to_call,
                current_bet=current_bet,
                min_raise_increment=min_raise_increment,
                pot=pot,
                contributions=contributions,
            )

            # If this was a raise, update current_bet and reset acted set
            if action == "raise" and player.bet > current_bet:
                min_raise_increment = player.bet - current_bet
                current_bet = player.bet
                acted = {player.name}
            else:
                acted.add(player.name)

            # Recalculate pot from contributions (single source of truth)
            pot = sum(contributions.values())

            action_log.append(log_entry)
            console.print(f"    {log_entry}")
            game_state.emit_action(
                self.hand_num, street, board,
                sum(contributions.values()), active, self._dealer_idx_snapshot,
                player, log_entry,
            )
            actions_taken += 1

        return pot, action_log

    def _apply_action(
        self,
        player: Player,
        action: str,
        amount: float,
        to_call: float,
        current_bet: float,
        min_raise_increment: float,
        pot: float,
        contributions: dict[Player, float],
    ) -> str:
        if action == "fold":
            player.folded = True
            return f"[red]{player.name}[/] folds"

        if action == "check":
            if to_call > 0:
                # Forced into a call
                return self._do_call(player, to_call, contributions)
            return f"[cyan]{player.name}[/] checks"

        if action == "call":
            return self._do_call(player, to_call, contributions)

        if action == "raise":
            # amount = desired total bet
            min_total = current_bet + min_raise_increment
            target = max(min_total, amount)
            target = min(player.stack + player.bet, target)
            additional = min(target - player.bet, player.stack)

            player.stack -= additional
            player.bet += additional
            contributions[player] = contributions.get(player, 0.0) + additional

            suffix = " [bold](all-in)[/]" if player.stack == 0 else ""
            if player.stack == 0:
                player.all_in = True
            return f"[green]{player.name}[/] raises to ${player.bet:.2f}{suffix}"

        # Unknown fallback → call/check
        if to_call > 0:
            return self._do_call(player, to_call, contributions)
        return f"[cyan]{player.name}[/] checks (default)"

    @staticmethod
    def _do_call(
        player: Player,
        to_call: float,
        contributions: dict[Player, float],
    ) -> str:
        actual = min(to_call, player.stack)
        player.stack -= actual
        player.bet += actual
        contributions[player] = contributions.get(player, 0.0) + actual

        if player.stack == 0:
            player.all_in = True
            return f"[cyan]{player.name}[/] calls ${actual:.2f} [bold](all-in)[/]"
        return f"[cyan]{player.name}[/] calls ${actual:.2f}"

    @staticmethod
    def _position_label(player: Player, active: list[Player]) -> str:
        try:
            idx = next(i for i, p in enumerate(active) if p.name == player.name)
            return f"seat {idx + 1}"
        except StopIteration:
            return "?"


# ------------------------------------------------------------------
# Display helpers
# ------------------------------------------------------------------

def _print_hand_header(hand_num: int, players: list[Player], dealer_idx: int) -> None:
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold magenta")
    t.add_column("Seat")
    t.add_column("Player")
    t.add_column("Model", style="dim")
    t.add_column("Stack", justify="right")
    t.add_column("Cards")

    for i, p in enumerate(players):
        marker = " [bold yellow]D[/]" if i == dealer_idx % len(players) else ""
        t.add_row(
            str(i + 1),
            p.name + marker,
            p.model.split("/")[-1],
            f"${p.stack:.2f}",
            p.cards_str,
        )

    console.print(Panel(t, title=f"[bold]Hand #{hand_num}[/]", border_style="blue"))


def _print_street(street: str, board: list[int], pot: float) -> None:
    board_str = engine.cards_to_str(board) if board else "(preflop)"
    console.print(
        f"\n  [bold]{street.upper()}[/]  Board: [white]{board_str}[/]  "
        f"Pot: [yellow]${pot:.2f}[/]"
    )


def _print_showdown(players: list[Player], board: list[int]) -> None:
    console.print("\n  [bold magenta]── SHOWDOWN ──[/]")
    for p in players:
        rank = engine.evaluate(p.hole_cards, board)
        desc = engine.rank_description(rank)
        console.print(f"  [cyan]{p.name}[/]: {p.cards_str}  →  [yellow]{desc}[/]")
