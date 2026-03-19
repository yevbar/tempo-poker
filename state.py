"""
Game state serialization. table.py calls emit() after key events;
server.py reads the file and streams it to connected browsers.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import re

from treys import Card

_RICH_TAG = re.compile(r'\[/?[a-zA-Z0-9 _#]+\]')

if TYPE_CHECKING:
    from player import Player

STATE_FILE = Path("game_state.json")
_lock = threading.Lock()

# Rolling action log (kept across hands so the UI has history)
_action_log: list[dict] = []
_MAX_LOG = 100


def _card_str(c: int) -> str:
    return Card.int_to_str(c)


def _serialize_player(
    p: Player,
    *,
    is_dealer: bool = False,
    is_active: bool = False,
    reveal_cards: bool = False,
) -> dict:
    hole_cards = None
    if reveal_cards and p.hole_cards and not p.folded:
        hole_cards = [_card_str(c) for c in p.hole_cards]

    return {
        "name": p.name,
        "model": p.model.split("/")[-1],
        "full_model": p.model,
        "stack": round(p.stack, 4),
        "bet": round(p.bet, 4),
        "folded": p.folded,
        "all_in": p.all_in,
        "is_dealer": is_dealer,
        "is_active": is_active,
        "hole_cards": hole_cards,
    }


def _write(state: dict) -> None:
    state["timestamp"] = datetime.now(timezone.utc).isoformat()
    state["action_log"] = _action_log[-_MAX_LOG:]
    with _lock:
        STATE_FILE.write_text(json.dumps(state))


def log_action(text: str, kind: str = "action") -> None:
    """Append an entry to the rolling action log (Rich markup stripped)."""
    _action_log.append({
        "text": _RICH_TAG.sub("", text).strip(),
        "kind": kind,  # "action" | "deal" | "street" | "win" | "system"
        "time": datetime.now(timezone.utc).isoformat(),
    })


def emit_waiting() -> None:
    _write({"status": "waiting", "message": "Waiting for game to start…"})


def emit_hand_start(
    hand_num: int,
    players: list[Player],
    dealer_idx: int,
    pot: float,
    sb_name: str,
    bb_name: str,
) -> None:
    log_action(f"── Hand #{hand_num} ──  SB: {sb_name}  BB: {bb_name}", kind="deal")
    _write({
        "status": "playing",
        "hand_num": hand_num,
        "street": "preflop",
        "pot": round(pot, 4),
        "board": [],
        "players": [
            _serialize_player(p, is_dealer=(i == dealer_idx))
            for i, p in enumerate(players)
        ],
    })


def emit_street(
    hand_num: int,
    street: str,
    board: list[int],
    pot: float,
    players: list[Player],
    dealer_idx: int,
    active_player: Player | None = None,
) -> None:
    log_action(f"{street.upper()}  board: {' '.join(_card_str(c) for c in board) if board else '—'}  pot: ${pot:.2f}", kind="street")
    _write({
        "status": "playing",
        "hand_num": hand_num,
        "street": street,
        "pot": round(pot, 4),
        "board": [_card_str(c) for c in board],
        "players": [
            _serialize_player(
                p,
                is_dealer=(i == dealer_idx),
                is_active=(active_player is not None and p.name == active_player.name),
            )
            for i, p in enumerate(players)
        ],
    })


def emit_action(
    hand_num: int,
    street: str,
    board: list[int],
    pot: float,
    players: list[Player],
    dealer_idx: int,
    acting_player: Player | None,
    log_entry: str,
    next_player: Player | None = None,
) -> None:
    log_action(log_entry, kind="action")
    _write({
        "status": "playing",
        "hand_num": hand_num,
        "street": street,
        "pot": round(pot, 4),
        "board": [_card_str(c) for c in board],
        "players": [
            _serialize_player(
                p,
                is_dealer=(i == dealer_idx),
                is_active=(next_player is not None and p.name == next_player.name),
            )
            for i, p in enumerate(players)
        ],
        "last_action": {"player": acting_player.name if acting_player else "", "text": log_entry},
    })


def emit_thinking(
    hand_num: int,
    street: str,
    board: list[int],
    pot: float,
    players: list[Player],
    dealer_idx: int,
    thinking_player: Player,
) -> None:
    """Mark a player as currently querying their LLM."""
    _write({
        "status": "playing",
        "hand_num": hand_num,
        "street": street,
        "pot": round(pot, 4),
        "board": [_card_str(c) for c in board],
        "players": [
            _serialize_player(
                p,
                is_dealer=(i == dealer_idx),
                is_active=(p.name == thinking_player.name),
            )
            for i, p in enumerate(players)
        ],
        "thinking": thinking_player.name,
    })


def emit_showdown(
    hand_num: int,
    board: list[int],
    pot: float,
    players: list[Player],
    dealer_idx: int,
    winnings: dict,
    hand_descs: dict[str, str],
) -> None:
    winner_names = [p.name for p, amt in winnings.items() if amt > 0]
    log_action(
        "SHOWDOWN  " + "  ".join(f"{p.name} +${amt:.2f}" for p, amt in winnings.items() if amt > 0),
        kind="win",
    )
    serialized = []
    for i, p in enumerate(players):
        d = _serialize_player(p, is_dealer=(i == dealer_idx), reveal_cards=True)
        d["won"] = round(winnings.get(p, 0.0), 4)
        d["hand_desc"] = hand_descs.get(p.name, "")
        d["is_winner"] = p.name in winner_names
        serialized.append(d)

    _write({
        "status": "showdown",
        "hand_num": hand_num,
        "street": "showdown",
        "pot": round(pot, 4),
        "board": [_card_str(c) for c in board],
        "players": serialized,
        "winners": winner_names,
    })


def emit_fold_win(
    hand_num: int,
    street: str,
    board: list[int],
    pot: float,
    players: list[Player],
    dealer_idx: int,
    winner: Player,
) -> None:
    log_action(f"{winner.name} wins ${pot:.2f} (all folded)", kind="win")
    serialized = []
    for i, p in enumerate(players):
        d = _serialize_player(p, is_dealer=(i == dealer_idx))
        d["won"] = round(pot if p.name == winner.name else 0.0, 4)
        d["is_winner"] = p.name == winner.name
        serialized.append(d)

    _write({
        "status": "showdown",
        "hand_num": hand_num,
        "street": street,
        "pot": round(pot, 4),
        "board": [_card_str(c) for c in board],
        "players": serialized,
        "winners": [winner.name],
    })
