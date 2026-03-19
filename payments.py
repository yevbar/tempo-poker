"""
Tempo wallet utilities for the poker game.

All LLM calls are made via `tempo request` which handles payment automatically
using the locally authenticated wallet (~/.tempo). No manual session key
management is needed.

To add funds: ~/.tempo/bin/tempo wallet fund
To check balance: ~/.tempo/bin/tempo wallet -t whoami
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

TEMPO_BIN = str(Path.home() / ".tempo" / "bin" / "tempo")


def wallet_info() -> dict:
    result = subprocess.run(
        [TEMPO_BIN, "wallet", "-j", "whoami"],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(result.stderr.strip() or "no output from tempo wallet whoami")
    return json.loads(result.stdout)


def print_wallet_summary() -> None:
    try:
        info = wallet_info()
        balance = info.get("balance", {})
        available = balance.get("available", "?")
        symbol = balance.get("symbol", "USDC")
        wallet = info.get("wallet", "?")
        short = wallet[:10] + "..." if len(wallet) > 10 else wallet
        print(f"Wallet {short}  Available: {available} {symbol}")
    except Exception as exc:
        print(f"Could not fetch wallet info: {exc}")


def check_tempo_ready() -> list[str]:
    """Return list of error strings. Empty = good to go."""
    errors = []
    try:
        info = wallet_info()
        balance = info.get("balance", {})
        available = float(balance.get("available", 0))
        if not info.get("ready", False):
            errors.append("Wallet not ready — run: ~/.tempo/bin/tempo wallet login")
        elif available <= 0:
            errors.append("Wallet balance is zero — run: ~/.tempo/bin/tempo wallet fund")
    except Exception as exc:
        errors.append(f"Tempo wallet error: {exc} — run: ~/.tempo/bin/tempo wallet login")
    return errors
