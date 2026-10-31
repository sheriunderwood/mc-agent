#!/usr/bin/env bash
# Starts the agent. Each secret (ANTHROPIC_API_KEY, MC_API_TOKEN) comes from:
#   1. the environment, if it's set (systemd sets it from the secrets file), else
#   2. ~/.config/mc-agent/secrets.env: KEY=value lines, readable only by you
#      (chmod 600). The usual place on Linux; works on macOS too. Else
#   3. on macOS, the Keychain: items <prefix>-anthropic-key and <prefix>-mc-token,
#      <prefix> being secrets.keychain_prefix in the data folder's config.toml.
# So secrets are never stored in a repo or in a service file.
#
# macOS one-time setup (each prompts for the value; nothing lands in shell history):
#   security add-generic-password -a "$USER" -s <prefix>-anthropic-key -w
#   security add-generic-password -a "$USER" -s <prefix>-mc-token -w
# Linux one-time setup: see DEPLOY.md, "Linux".
#
# Usage: ./run.sh [agent.py options], e.g. ./run.sh --observe-only --once
# (bash 3.2, as macOS ships, or newer.)

# Started by another shell (e.g. an older service file running zsh)? Re-run under bash.
if [ -z "${BASH_VERSION:-}" ]; then exec /bin/bash "$0" "$@"; fi

set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PREFIX="$(.venv/bin/python config.py keychain_prefix)"
SECRETS="$(.venv/bin/python config.py secrets_file)"   # moves the old ~/.config/mcsl-agent there first

if [[ -f "$SECRETS" ]] && [[ -n "$(find "$SECRETS" -perm -004 -o -perm -040 2>/dev/null)" ]]; then
  echo "Warning: $SECRETS can be read by other users. Fix it with: chmod 600 \"$SECRETS\"" >&2
fi

load_secret() {   # load_secret NAME keychain-suffix
  local name="$1" suffix="$2" line value
  [[ -n "${!name:-}" ]] && { export "$name"; return 0; }
  if [[ -f "$SECRETS" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      line="${line#export }"
      if [[ "$line" == "$name="* ]]; then
        value="${line#*=}"; value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
        if [[ -n "$value" ]]; then printf -v "$name" '%s' "$value"; export "$name"; return 0; fi
      fi
    done < "$SECRETS"
  fi
  if [[ "$(uname)" == Darwin ]] && value="$(security find-generic-password -a "$USER" -s "$PREFIX-$suffix" -w 2>/dev/null)"; then
    printf -v "$name" '%s' "$value"; export "$name"; return 0
  fi
  echo "No $name in the environment, $SECRETS, or (macOS) the Keychain item $PREFIX-$suffix." >&2
  exit 1
}

load_secret MC_API_TOKEN mc-token

# First run (no config.toml yet): set up the data folder from the avatar MC is
# connected to, offer someone nearby as owner, then stop so it can be checked.
if [[ ! -f "$(.venv/bin/python config.py config_file)" ]]; then
  .venv/bin/python first_run.py
  exit $?
fi

load_secret ANTHROPIC_API_KEY anthropic-key

exec .venv/bin/python agent.py "$@"
