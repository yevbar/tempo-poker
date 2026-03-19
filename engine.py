"""
Pure poker logic: deck management, hand evaluation, side pot calculation.
No LLM or Tempo dependencies.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from treys import Card, Deck, Evaluator

if TYPE_CHECKING:
    from player import Player

_evaluator = Evaluator()


# ---------------------------------------------------------------------------
# Card helpers
# ---------------------------------------------------------------------------

def cards_to_str(cards: list[int]) -> str:
    """Human-readable card string, e.g. 'A♠ K♥'."""
    return " ".join(Card.int_to_pretty_str(c) for c in cards)


def new_deck() -> list[int]:
    d = Deck()
    d.shuffle()
    return list(d.cards)


def draw(deck: list[int], n: int) -> list[int]:
    drawn = deck[:n]
    del deck[:n]
    return drawn


# ---------------------------------------------------------------------------
# Hand evaluation
# ---------------------------------------------------------------------------

def evaluate(hole: list[int], board: list[int]) -> int:
    """Return numeric rank (lower = better). Requires board >= 3 cards."""
    return _evaluator.evaluate(board, hole)


def rank_description(rank: int) -> str:
    return _evaluator.class_to_string(_evaluator.get_rank_class(rank))


def best_hands(players: list[Player], board: list[int]) -> list[Player]:
    """Return list of winners (multiple on tie). Board must have 5 cards."""
    ranked = [(p, evaluate(p.hole_cards, board)) for p in players]
    best = min(r for _, r in ranked)
    return [p for p, r in ranked if r == best]


# ---------------------------------------------------------------------------
# Side pot calculation
# ---------------------------------------------------------------------------

@dataclass
class Pot:
    amount: float
    eligible: list  # list of Player objects


def calculate_pots(contributions: dict) -> list[Pot]:
    """
    contributions: {player: total_chips_put_in_this_hand}
    Returns a list of Pot objects (main pot first, then side pots).
    Folded players contribute to pots but cannot win them.
    """
    if not contributions:
        return []

    levels = sorted(set(contributions.values()))
    pots: list[Pot] = []
    prev = 0.0

    for level in levels:
        if level <= prev:
            continue

        amount = sum(
            max(0.0, min(c, level) - prev)
            for c in contributions.values()
        )
        eligible = [
            p for p, c in contributions.items()
            if not p.folded and c >= level
        ]

        if amount > 0 and eligible:
            pots.append(Pot(amount=round(amount, 6), eligible=eligible))

        prev = level

    return pots


def distribute_pots(pots: list[Pot], board: list[int]) -> dict:
    """
    Evaluate each pot and award chips to winner(s).
    Returns {player: amount_won}.
    """
    winnings: dict = {}

    for pot in pots:
        if not pot.eligible:
            continue

        if len(pot.eligible) == 1:
            winners = pot.eligible
        else:
            winners = best_hands(pot.eligible, board)

        share = round(pot.amount / len(winners), 6)
        for w in winners:
            winnings[w] = winnings.get(w, 0.0) + share

    return winnings
