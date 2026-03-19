#!/usr/bin/env bash
set -e

# Install Tempo CLI if not present
if [ ! -f "$HOME/.tempo/bin/tempo" ]; then
  echo "Installing Tempo CLI..."
  curl -fsSL https://tempo.xyz/install | bash || true
fi

export PATH="$HOME/.tempo/bin:$PATH"

# Restore Tempo wallet keys from env var
if [ -n "$TEMPO_KEYS_TOML" ]; then
  mkdir -p ~/.tempo/wallet
  echo "$TEMPO_KEYS_TOML" | base64 -d > ~/.tempo/wallet/keys.toml
  echo "Tempo wallet restored."
else
  echo "WARNING: TEMPO_KEYS_TOML not set — LLM calls will fail."
fi

exec python game.py --ui --port "${PORT:-8080}"
