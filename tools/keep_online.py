"""Log the avatar back in if Morgen Commander is running but the avatar is
offline, unless the owner put it on a break. Only when config.toml has
[mc] keep_online = true; otherwise it does nothing.

Run every 5 minutes by its own service (deploy/install.sh --online: launchd
com.mcsl.<avatar>.online, or the mcsl-online timer), logging to logs/online.log.

Headless MC (--login) already logs the avatar back in when the grid drops it;
this is the backstop for anything else. It prints one line, or nothing when
all is well.
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agent                                # noqa: E402
import config                               # noqa: E402


def say(text: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} online: {text}", flush=True)


async def main() -> None:
    if not config.KEEP_ONLINE:
        return
    token = config.secret("MC_API_TOKEN")
    if not token:
        say(f"no MC_API_TOKEN (environment, {config.SECRETS_FILE} or Keychain); can't check")
        return
    port = int(os.environ.get("MC_API_PORT", "47174"))
    try:
        status = await agent.mc_call(token, port, "status", {})
    except Exception as e:                  # MC not running: its service restarts it
        say(f"Morgen Commander isn't answering ({type(e).__name__}); its service should restart it")
        return
    if status.get("online"):
        return
    if b := agent.current_break():
        say(f"offline, on a break{' until ' + b['until'] if b.get('until') else ''}: leaving it")
        return
    r = await agent.mc_call(token, port, "login", {"start": "last"})
    say(f"was offline; logging back in: {r.get('said') or r.get('error') or r}")


if __name__ == "__main__":
    asyncio.run(main())
