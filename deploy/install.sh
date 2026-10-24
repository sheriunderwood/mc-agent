#!/usr/bin/env bash
# Installs (or reinstalls) the services for this checkout, so the machine runs
# everything on its own: launchd on macOS, systemd user units on Linux.
#
#   deploy/install.sh --all [-- ARGS]       headless Morgen Commander + the agent + shopping
#                                           (+ keep-online, if config.toml has [mc] keep_online = true)
#   deploy/install.sh --mc                  Morgen Commander headless (no window), avatar logged in
#   deploy/install.sh --agent [-- ARGS]     the agent; ARGS go to run.sh, e.g. -- --daily-budget 20
#   deploy/install.sh --online              every 5 minutes, log the avatar back in if it's offline
#                                           (tools/keep_online.py; needs [mc] keep_online = true)
#   deploy/install.sh --shop                every 15 minutes, research the stores the agent noted,
#                                           and re-check every SLURL once a day (tools/shop_lookup.py due)
#   deploy/install.sh --uninstall [WHAT]    remove mc, agent, online, shop, or all (the default)
#   deploy/install.sh --status              what's installed and running
#
# Reinstalling replaces a service (e.g. to change the agent's ARGS).
# DRY_RUN=1 deploy/install.sh ... prints the service files instead of installing them.
#
# The data folder (config.py finds it; set MCSL_HOME for another) is passed to the
# services as MCSL_HOME.
# macOS: com.mcsl.<avatar>.{mc,agent,online,shop} in ~/Library/LaunchAgents.
# Linux: mcsl-{mc,agent,online,shop} in ~/.config/systemd/user (online and shop as .timers).
#   They need lingering, so they run with nobody logged in; an admin runs once:
#   sudo loginctl enable-linger <user>
# (bash 3.2, as macOS ships, or newer.)

# Started by another shell (e.g. an older service file running zsh)? Re-run under bash.
if [ -z "${BASH_VERSION:-}" ]; then exec /bin/bash "$0" "$@"; fi

set -euo pipefail
# The code dir is the one above this deploy/ folder; the avatar's data — config, logs, pid file —
# sits in the data dir, which config.py finds: $MCSL_HOME, or the user's default (see config.py).
# The services get it as MCSL_HOME, so they always agree.
CODE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$CODE/.venv/bin/python"
DATA="$("$PY" "$CODE/config.py" data_dir)"
AVATAR="$("$PY" "$CODE/config.py" avatar)"
SLUG="$("$PY" "$CODE/config.py" avatar_slug)"      # the avatar's name, safe for service labels
MC_BIN="$("$PY" "$CODE/config.py" mc_command)"
if [[ "$(uname)" == Darwin ]]; then OS=mac; else OS=linux; fi

say() { printf '%s\n' "$*"; }
err() { printf '%s\n' "$*" >&2; }

# ---------------------------------------------------------------- per-OS service handling

if [[ "$OS" == mac ]]; then
  UNITS="$HOME/Library/LaunchAgents"
  DOMAIN="gui/$(id -u)"
  name()      { printf 'com.mcsl.%s.%s' "$SLUG" "$1"; }
  template()  { printf '%s' "$CODE/deploy/launchd/mcsl-$1.plist"; }
  unit_file() { printf '%s' "$UNITS/$(name "$1").plist"; }
  running()   { launchctl print "$DOMAIN/$(name "$1")" >/dev/null 2>&1; }
  remove() {
    launchctl bootout "$DOMAIN/$(name "$1")" 2>/dev/null || true
    rm -f "$(unit_file "$1")"
  }
  activate() { launchctl bootstrap "$DOMAIN" "$(unit_file "$1")"; }
  pid_of() { launchctl print "$DOMAIN/$(name "$1")" 2>/dev/null | awk '/^\tpid =/ {print $3}'; }
else
  UNITS="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  name()      { printf 'mcsl-%s' "$1"; }
  # Keep-online and shopping run from timers: their service files are installed alongside.
  timed()     { case "$1" in online|shop) return 0 ;; *) return 1 ;; esac; }
  unit()      { if timed "$1"; then printf 'mcsl-%s.timer' "$1"; else printf 'mcsl-%s.service' "$1"; fi; }
  template()  { printf '%s' "$CODE/deploy/systemd/$(unit "$1")"; }
  unit_file() { printf '%s' "$UNITS/$(unit "$1")"; }
  running()   { systemctl --user is-active --quiet "$(unit "$1")" 2>/dev/null; }
  remove() {
    systemctl --user disable --now "$(unit "$1")" 2>/dev/null || true
    rm -f "$(unit_file "$1")"
    if timed "$1"; then rm -f "$UNITS/mcsl-$1.service"; fi
    systemctl --user daemon-reload 2>/dev/null || true
  }
  activate() { systemctl --user daemon-reload; systemctl --user enable --now "$(unit "$1")"; }
  pid_of() { systemctl --user show -p MainPID --value "$(unit "$1")" 2>/dev/null | grep -v '^0$' || true; }
fi

# The MC window (no arguments), as opposed to headless MC or the agent's `--mcp` helpers.
# (grep without -q: with pipefail, -q stopping early makes ps fail and the check say no.)
mc_window_open() { ps -eww -o args= 2>/dev/null | grep -E '/MorgenCommander$' >/dev/null; }

# An agent started by hand (run.sh in a terminal), not by the service manager.
agent_by_hand() {
  [[ -f "$DATA/agent.pid" ]] || return 1
  local pid; pid="$(<"$DATA/agent.pid")"
  kill -0 "$pid" 2>/dev/null && ! running agent
}

# Fill in a template: __CODE__ (the code dir) and __DATA__ (the data dir), plus
# __AVATAR__, __SLUG__ (its name for service labels), __MC__, and __ARGS__ (each
# argument escaped for the file type).
# In Python: arguments may hold characters sed would mangle.
render() {   # render TEMPLATE [ARGS...]
  CODE="$CODE" DATA="$DATA" AVATAR="$AVATAR" SLUG="$SLUG" MC_BIN="$MC_BIN" "$PY" - "$@" <<'PY'
import os, sys
from xml.sax.saxutils import escape
path, args = sys.argv[1], sys.argv[2:]
text = open(path).read()
if path.endswith(".plist"):
    val, joined = escape, "".join(f"<string>{escape(a)}</string>" for a in args)
else:   # systemd: quoted words; % is systemd's specifier character
    val = lambda s: s.replace("%", "%%")
    joined = " ".join('"' + a.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"' for a in args)
for key, value in (("__CODE__", os.environ["CODE"]), ("__DATA__", os.environ["DATA"]),
                   ("__AVATAR__", os.environ["AVATAR"]), ("__SLUG__", os.environ["SLUG"]),
                   ("__MC__", os.environ["MC_BIN"])):
    text = text.replace(key, val(value))
print(text.replace("__ARGS__", joined), end="")
PY
}

install_one() {   # install_one mc|agent|online|shop [ARGS...]
  local what="$1"; shift
  local text extra=""
  text="$(render "$(template "$what")" "$@")"
  if [[ "$OS" == linux ]] && timed "$what"; then
    extra="$(render "$CODE/deploy/systemd/mcsl-$what.service")"
  fi
  if [[ -n "${DRY_RUN:-}" ]]; then
    say "== $(unit_file "$what")"; say "$text"
    if [[ -n "$extra" ]]; then say "== $UNITS/mcsl-$what.service"; say "$extra"; fi
    return 0
  fi
  remove "$what"
  mkdir -p "$UNITS" "$DATA/logs"
  printf '%s\n' "$text" > "$(unit_file "$what")"
  if [[ -n "$extra" ]]; then printf '%s\n' "$extra" > "$UNITS/mcsl-$what.service"; fi
  activate "$what"
  say "Installed $(name "$what"). Log: $DATA/logs/$what.log"
}

linger_off() {
  [[ "$OS" == linux ]] && [[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != yes ]]
}

status() {
  local w state pid
  local list="mc agent online shop"
  for w in $list; do
    if running "$w"; then
      pid="$(pid_of "$w")"; state="running${pid:+ (pid $pid)}"
    elif [[ -f "$(unit_file "$w")" ]]; then
      state="installed, not running"
    else
      state="not installed"
    fi
    say "$(name "$w"): $state"
  done
  if mc_window_open; then say "Morgen Commander's window is open."; fi
  if agent_by_hand; then say "An agent is running by hand (in a terminal)."; fi
  if linger_off; then
    say "Lingering is off: these services stop when you log out. An admin runs once: sudo loginctl enable-linger $USER"
  fi
  return 0
}

# ---------------------------------------------------------------- what to do

KEEP_ONLINE="$("$PY" "$CODE/config.py" keep_online)"
want_mc=0; want_agent=0; want_online=0; want_shop=0; agent_args=()
case "${1:-}" in
  --all)       want_mc=1; want_agent=1; want_shop=1; [[ "$KEEP_ONLINE" == yes ]] && want_online=1; shift ;;
  --mc)        want_mc=1; shift ;;
  --agent)     want_agent=1; shift ;;
  --online)    want_online=1; shift ;;
  --shop)      want_shop=1; shift ;;
  --status)    status; exit 0 ;;
  --uninstall)
    case "${2:-all}" in
      all)            remove agent; remove mc; remove online; remove shop; say "Uninstalled everything." ;;
      mc|agent|online|shop)  remove "$2"; say "Uninstalled $(name "$2")." ;;
      *)              err "What to uninstall: mc, agent, online, shop or all"; exit 2 ;;
    esac
    exit 0 ;;
  *) err "Usage: see the top of deploy/install.sh"; exit 2 ;;
esac
if (( want_agent )) && [[ "${1:-}" == "--" ]]; then shift; agent_args=("$@"); fi

# Linux: systemctl --user needs this user's systemd and its session bus. A
# shell from su/sudo -u has neither until lingering is on and two variables
# point at them; say so instead of systemctl's "Failed to connect to bus".
if [[ "$OS" == linux && -z "${DRY_RUN:-}" ]] && ! systemctl --user show-environment >/dev/null 2>&1; then
  err "Can't reach $USER's systemd (systemctl --user). Usually one of:"
  err "  - lingering is off. An admin runs once: sudo loginctl enable-linger $USER"
  err "  - this shell came from su or sudo -u. SSH in as $USER instead, or set:"
  err "      export XDG_RUNTIME_DIR=/run/user/\$(id -u)"
  err "      export DBUS_SESSION_BUS_ADDRESS=unix:path=\$XDG_RUNTIME_DIR/bus"
  err "  - the package dbus-user-session isn't installed (an admin: sudo apt install dbus-user-session)."
  exit 1
fi

# A data folder that must never run the services (e.g. a developer's copy of a
# live avatar's data) has a .no-services file: only DRY_RUN works there.
if [[ -f "$DATA/.no-services" && -z "${DRY_RUN:-}" ]]; then
  err "Not installing: the data folder has a .no-services file (a development machine). DRY_RUN=1 still works."
  exit 1
fi

if (( want_mc )); then
  if mc_window_open; then
    err "Morgen Commander's window is open. Quit it first: the window and headless MC can't run at once."
    exit 1
  fi
  [[ -n "$AVATAR" ]] || { err "No avatar name in config.toml ([avatar] name)."; exit 1; }
  [[ -x "$MC_BIN" ]] || { err "Morgen Commander isn't at $MC_BIN. Set [mc] command in config.toml."; exit 1; }
fi
if (( want_mc || want_agent || want_online || want_shop )) && [[ ! -f "$DATA/config.toml" ]]; then
  err "No config.toml in the data folder ($DATA). Set it up first: $PY $CODE/init.py"
  exit 1
fi
if (( want_online )) && [[ "$KEEP_ONLINE" != yes ]]; then
  err "keep_online is off: set [mc] keep_online = true in config.toml (or config.local.toml) first."
  exit 1
fi
if (( want_agent )) && agent_by_hand; then
  err "An agent is already running by hand. Stop it first (Ctrl-C in its terminal), or there'd be two."
  exit 1
fi

if (( want_mc )); then install_one mc; fi
if (( want_agent )); then install_one agent ${agent_args[@]+"${agent_args[@]}"}; fi
if (( want_online )); then install_one online; fi
if (( want_shop )); then install_one shop; fi
if (( want_mc )) && [[ -z "${DRY_RUN:-}" ]]; then
  say "MC logs $AVATAR in with its saved login. If $DATA/logs/mc.log says there's none, save it once:"
  if [[ "$OS" == linux ]]; then say "  \"$MC_BIN\" --save-login \"$AVATAR\" --in-file"
  else say "  \"$MC_BIN\" --save-login \"$AVATAR\""; fi
fi
if [[ -z "${DRY_RUN:-}" ]] && linger_off; then
  say "Note: lingering is off, so these stop when you log out. An admin runs once: sudo loginctl enable-linger $USER"
fi
exit 0
