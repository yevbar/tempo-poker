#!/usr/bin/env bash
set -e

# Restore Tempo wallet from env var
if [ -n "$TEMPO_KEYS_TOML" ]; then
  mkdir -p ~/.tempo/wallet
  echo "$TEMPO_KEYS_TOML" | base64 -d > ~/.tempo/wallet/keys.toml
  echo "Tempo wallet restored."
else
  echo "WARNING: TEMPO_KEYS_TOML not set — LLM calls will fail."
fi

exec python game.py --ui --port "${PORT:-8080}"
