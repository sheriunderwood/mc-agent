"""Where the agent's data lives, and the settings for this deployment.

The code and the data are kept apart, so the agent can be shared without
anyone's data:

- The data folder holds one avatar's world: config.toml, persona.md, RULES.md,
  OWNERS.md, FRIENDS.md, friends/, reports/, state, logs and so on. It's, in
  order: $MCSL_HOME; the folder around the code's, if it holds config.toml
  and OWNERS.md (a checkout with the data around the code); or the user's own
  data folder: ~/Library/Application Support/mc-agent on macOS,
  ~/.local/share/mc-agent on Linux ($XDG_DATA_HOME). `python init.py` sets
  one up.
- config.toml in it says who the avatar is and how the agent behaves there
  (see config.example.toml). Anything left out uses the defaults below.
"""

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent      # …/app — the code

APP_NAME = "mc-agent"


def default_data_dir() -> Path:
    """This user's data folder for the agent, when nothing else says where."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_NAME


def find_data_dir() -> Path:
    """$MCSL_HOME, else the folder around the code's if it's an avatar's data, else the default."""
    if os.environ.get("MCSL_HOME"):
        return Path(os.environ["MCSL_HOME"]).expanduser().resolve()
    around = CODE_DIR.parent
    if (around / "config.toml").is_file() and (around / "OWNERS.md").is_file():
        return around.resolve()
    return default_data_dir()


DATA_DIR = find_data_dir()
CONFIG_FILE = DATA_DIR / "config.toml"
LOCAL_CONFIG_FILE = DATA_DIR / "config.local.toml"   # this machine only: overrides config.toml

DEFAULTS = {
    "avatar": {
        "name": "",            # the account name the agent drives
        "uuid": "",
        "call_names": "",      # regex: words in local chat that mean someone's talking to the avatar
    },
    "home": {
        "region": "",          # where the avatar lives: greets everyone there, scans outfits there
        "parcel": "",
        "slurl": "",           # its landing point, sent by club_link to anyone (not blocked) who asks
        "landmark": "",        # inventory path of its landmark, for club_link; empty: found by name
    },
    "chat": {
        "crowd_limit": 40,     # more people than this within chat range: local chat is filtered
        "chat_range_m": 20,
        "owner_model": "smart",   # "chat": the chat model (Haiku) answers owner messages too
    },
    "greeting": {
        "range_m": 50,         # greet people within this distance
        "poll_seconds": 20,    # how often the program looks who's nearby (no AI)
        "moved_m": 1.5,        # someone has moved (rezzed, can interact) once this far from where they were
        "settle_seconds": 60,  # wait this long after a friend logs in
    },
    "huds": {
        "dance_channel": 34336,
        "wearing_channel": 34337,
        "extra_commanders": [],  # UUIDs besides the avatar and owners who may command the dance HUD
    },
    "mc": {
        "command": "",         # Morgen Commander's program; default: the usual place for this OS
        "keep_online": False,  # every 5 min, log the avatar back in if MC is up but it's offline (no break)
    },
    "secrets": {
        "keychain_prefix": "mcsl-agent",   # macOS Keychain items <prefix>-anthropic-key and <prefix>-mc-token
        "desktop_server": "",              # fallback: the MC token from this Claude desktop MCP server's config
    },
    "friendship": {
        "accept_from": [],     # UUIDs whose friendship offers the avatar may accept without an owner
    },
}


def _load() -> dict:
    """Defaults, then config.toml, then config.local.toml (settings for this
    machine only, such as [mc] command or keep_online; git ignores it)."""
    settings = {section: dict(values) for section, values in DEFAULTS.items()}
    for path in (CONFIG_FILE, LOCAL_CONFIG_FILE):
        if path.exists():
            with path.open("rb") as f:
                for section, values in tomllib.load(f).items():
                    if isinstance(values, dict):
                        settings.setdefault(section, {}).update(values)
    return settings


SETTINGS = _load()


def get(section: str, key: str):
    return SETTINGS.get(section, {}).get(key, DEFAULTS.get(section, {}).get(key))


AVATAR = get("avatar", "name")
AVATAR_UUID = str(get("avatar", "uuid")).lower()
CALL_NAMES = get("avatar", "call_names") or (AVATAR and AVATAR.split()[0]) or ""
HOME_REGION = get("home", "region")
HOME_PARCEL = get("home", "parcel")
HOME_SLURL = get("home", "slurl").strip()
HOME_LANDMARK = get("home", "landmark").strip()
KEYCHAIN_PREFIX = get("secrets", "keychain_prefix")
FRIENDSHIP_ACCEPT_FROM = {str(u).strip().lower() for u in get("friendship", "accept_from") or []} - {""}

# Secrets on Linux (and anywhere without a Keychain): KEY=value lines in this
# file, readable only by the avatar's user. systemd loads it into the agent's
# environment (EnvironmentFile=); run.sh sources it when run by hand.
SECRETS_FILE = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "mcsl-agent" / "secrets.env"
_KEYCHAIN_NAMES = {"ANTHROPIC_API_KEY": "anthropic-key", "MC_API_TOKEN": "mc-token"}


def mc_command() -> str:
    """Morgen Commander's program: config [mc] command, else where it usually is."""
    if cmd := get("mc", "command"):
        return str(Path(cmd).expanduser())
    if sys.platform == "darwin":
        return "/Applications/Morgen Commander.app/Contents/MacOS/MorgenCommander"
    return shutil.which("MorgenCommander") or str(Path.home() / "MorgenCommander" / "MorgenCommander")


def secret(name: str) -> str:
    """A secret (ANTHROPIC_API_KEY, MC_API_TOKEN): the environment, else the
    secrets file, else (macOS) the Keychain item <prefix>-<name>. "" if none."""
    if os.environ.get(name):
        return os.environ[name]
    if SECRETS_FILE.exists():
        for line in SECRETS_FILE.read_text().splitlines():
            key, _, value = line.strip().removeprefix("export ").partition("=")
            if key.strip() == name and value.strip():
                return value.strip().strip("'\"")
    if sys.platform == "darwin" and name in _KEYCHAIN_NAMES:
        try:
            return subprocess.run(["security", "find-generic-password", "-a", os.environ.get("USER", ""),
                                   "-s", f"{KEYCHAIN_PREFIX}-{_KEYCHAIN_NAMES[name]}", "-w"],
                                  capture_output=True, text=True, check=True).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    return ""


MC_COMMAND = mc_command()
KEEP_ONLINE = bool(get("mc", "keep_online"))


if __name__ == "__main__":
    # For shell scripts: python config.py keychain_prefix
    import sys
    wanted = sys.argv[1] if len(sys.argv) > 1 else ""
    import re
    slug = re.sub(r"[^a-z0-9.-]+", "-", (AVATAR or "").lower()).strip("-.") or "agent"   # for service labels
    print({"keychain_prefix": KEYCHAIN_PREFIX, "data_dir": str(DATA_DIR), "avatar": AVATAR, "avatar_slug": slug,
           "mc_command": MC_COMMAND, "keep_online": "yes" if KEEP_ONLINE else "no",
           "secrets_file": str(SECRETS_FILE)}.get(wanted, ""))
