"""
LLM-backed poker player. Uses `tempo request` to call OpenRouter with automatic
Tempo payment handling — no manual session key management required.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from engine import cards_to_str

logger = logging.getLogger(__name__)

TEMPO_BIN = str(Path.home() / ".tempo" / "bin" / "tempo")
OPENROUTER_URL = "https://openrouter.mpp.tempo.xyz/v1/chat/completions"
TURN_TIMEOUT = 10  # seconds; player forfeits to check/call on timeout


@dataclass(eq=False)
class Player:
    name: str
    model: str       # any OpenRouter model, e.g. "openai/gpt-4o"
    stack: float     # current chip count in USDC

    # Per-hand state
    hole_cards: list[int] = field(default_factory=list)
    folded: bool = False
    all_in: bool = False

    # Per-street state
    bet: float = 0.0

    # Lifetime stats
    hands_played: int = 0
    total_won: float = 0.0

    def reset_for_hand(self) -> None:
        self.hole_cards = []
        self.folded = False
        self.all_in = False
        self.bet = 0.0

    def reset_for_street(self) -> None:
        self.bet = 0.0

    @property
    def cards_str(self) -> str:
        return cards_to_str(self.hole_cards) if self.hole_cards else "?? ??"

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------

    def decide(self, game_state: dict) -> dict:
        """
        Ask the LLM what to do. Returns a validated action dict:
          {"action": "fold"|"check"|"call"|"raise", "amount": float}
        Falls back to check/call if the LLM times out or errors.
        """
        prompt = self._build_prompt(game_state)
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an expert poker player making decisions for real USDC stakes. "
                        "Always respond with valid JSON and nothing else."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 150,
            "temperature": 0.8,
        })

        try:
            proc = subprocess.run(
                [TEMPO_BIN, "request", "-X", "POST", "--json", payload, OPENROUTER_URL],
                capture_output=True,
                text=True,
                timeout=TURN_TIMEOUT,
            )
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.strip() or "non-zero exit")

            raw = json.loads(proc.stdout)["choices"][0]["message"]["content"]
            result = json.loads(raw)
            action = self._validate(result, game_state)
            logger.debug(
                "%s (%s) → %s [%s]",
                self.name,
                self.model.split("/")[-1],
                action,
                result.get("reasoning", ""),
            )
            return action

        except subprocess.TimeoutExpired:
            logger.warning("%s timed out (>%ds), defaulting.", self.name, TURN_TIMEOUT)
        except Exception as exc:
            logger.warning("%s LLM error (%s), defaulting.", self.name, exc)

        return self._default_action(game_state)

    def _validate(self, result: dict, gs: dict) -> dict:
        action = str(result.get("action", "")).lower().strip()
        to_call = float(gs.get("to_call", 0))
        min_raise = float(gs.get("min_raise", to_call * 2 or self._bb(gs)))

        if action == "fold":
            return {"action": "fold", "amount": 0.0}

        if action == "check":
            if to_call > 0:
                return self._make_call(to_call)
            return {"action": "check", "amount": 0.0}

        if action == "call":
            return self._make_call(to_call)

        if action in ("raise", "all_in"):
            target = self.stack + self.bet if action == "all_in" else float(result.get("amount", min_raise))
            target = max(min_raise, target)
            target = min(self.stack + self.bet, target)
            additional = min(target - self.bet, self.stack)
            return {"action": "raise", "amount": round(self.bet + additional, 6)}

        return self._default_action(gs)

    def _make_call(self, to_call: float) -> dict:
        return {"action": "call", "amount": round(min(to_call, self.stack), 6)}

    def _default_action(self, gs: dict) -> dict:
        to_call = float(gs.get("to_call", 0))
        if to_call == 0:
            return {"action": "check", "amount": 0.0}
        return self._make_call(to_call)

    @staticmethod
    def _bb(gs: dict) -> float:
        return float(gs.get("big_blind", 0.10))

    # ------------------------------------------------------------------
    # Prompt
    # ------------------------------------------------------------------

    def _build_prompt(self, gs: dict) -> str:
        community = gs.get("community_cards", [])
        community_str = cards_to_str(community) if community else "(none yet)"
        to_call = float(gs.get("to_call", 0))
        pot = float(gs.get("pot", 0))
        min_raise = float(gs.get("min_raise", to_call * 2))
        street = gs.get("street", "preflop")

        others = gs.get("other_players", [])
        others_lines = "\n".join(
            "  {:12s} stack=${:.2f}  {}".format(
                p["name"] + ":",
                p["stack"],
                "FOLDED" if p["folded"] else f"bet=${p['bet']:.2f}",
            )
            for p in others
        )

        recent = gs.get("recent_actions", [])
        recent_str = "\n  ".join(recent[-5:]) if recent else "(start of street)"

        actions = []
        if to_call == 0:
            actions.append("check")
        else:
            actions.append(f"call ${to_call:.2f}")
        actions.append(f"raise (min total ${min_raise:.2f}, max ${self.stack + self.bet:.2f})")
        actions.append("fold")

        return f"""=== Texas Hold'em — {street.upper()} ===

Your name   : {self.name}
Your hand   : {self.cards_str}
Board       : {community_str}
Your stack  : ${self.stack:.2f} USDC
Your bet    : ${self.bet:.2f}
Pot         : ${pot:.2f} USDC
To call     : ${to_call:.2f}
Position    : {gs.get("position", "?")} of {gs.get("num_active", "?")}

Other players:
{others_lines}

Recent actions:
  {recent_str}

Available: {" | ".join(actions)}

Respond ONLY with JSON:
{{"action": "fold"|"check"|"call"|"raise"|"all_in", "amount": <raise_to_total_if_raising>, "reasoning": "<1 sentence>"}}"""
