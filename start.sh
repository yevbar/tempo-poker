#!/usr/bin/env bash
set -e

# Install Tempo CLI if not present
export PATH="$HOME/.tempo/bin:$PATH"
if [ ! -f "$HOME/.tempo/bin/tempo" ]; then
  echo "Installing Tempo CLI..."
  curl -fsSL https://tempo.xyz/install | bash || true
  # Run tempoup to download the actual tempo binary
  "$HOME/.tempo/bin/tempoup" || true
  # Wait up to 60s for the binary to appear
  for i in $(seq 1 60); do
    [ -f "$HOME/.tempo/bin/tempo" ] && break
    echo "Waiting for tempo binary... ($i/60)"
    sleep 1
  done
fi

# Restore Tempo wallet keys from env var
if [ -n "$TEMPO_KEYS_TOML" ]; then
  mkdir -p ~/.tempo/wallet
  echo "$TEMPO_KEYS_TOML" | base64 -d > ~/.tempo/wallet/keys.toml
  echo "Tempo wallet restored."
else
  echo "WARNING: TEMPO_KEYS_TOML not set — LLM calls will fail."
fi

exec python game.py --ui --port "${PORT:-8080}"
