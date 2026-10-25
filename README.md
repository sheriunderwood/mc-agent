# mc-agent

An AI companion for your Second Life avatar. It runs your avatar on its own,
through [Morgen Commander](https://morgencommander.com)'s MCP server, with
Anthropic's Claude doing the talking:

- **Chats** in local chat and IMs, in the voice you give it (`persona.md`).
- **Greets** people at your home club or venue, and hands out its landmark or
  SLURL to anyone who asks.
- **Remembers** the people it meets (their pronouns, interests, favourite
  DJs) in plain Markdown files you can read and edit.
- **Dances** with friends, and runs an optional dance HUD for a whole group.
- **Notices** outfits with an optional "what are they wearing" HUD, and keeps a
  shopping list of stores people mention.
- **Reports** what happened each day, and queues anything only you can decide
  (offers, friend requests, changes) for your approval.

You stay in charge: only **owners**, identified by UUID, can tell it to
teleport, accept things, wear things or log out, and only by IM. Those limits
are enforced by the program, not just by the AI's instructions (see
[Security](#security)).

> Not affiliated with Linden Lab or with Morgen Commander. Second Life is a
> trademark of Linden Research, Inc.

## Before you start

- **A Second Life account for the avatar.** Read Linden Lab's policy on
  automated avatars ("bots") first: they must be registered as **scripted
  agents** in the account's settings on secondlife.com, and some places don't
  allow bots at all. You're responsible for how your avatar behaves.
- **Morgen Commander 1.4.2 or later** (the latest is best), a text-based
  Second Life viewer with a built-in MCP server.
- **An Anthropic API key** from the [Claude Console](https://console.anthropic.com).
  The agent uses the API, which is billed by use: see [Costs](#costs).
- **A Mac or a Linux computer** that stays on while the avatar is online, with
  **Python 3.12 or later** and git.

## 1. Install Morgen Commander

Download it from [morgencommander.com](https://morgencommander.com) (the
[release notes](https://morgencommander.com/releases) list what's new).

- **Mac:** put it in `/Applications`.
- **Linux:** unpack the tarball to `~/MorgenCommander/` (use the tarball, so
  it can update itself). Elsewhere is fine too; then set `[mc] command` in
  your config (step 4).

Log your avatar in once in Morgen Commander's window and tick **Remember
password**. On a Linux server without a desktop, save the login on the command
line instead (it asks for the password once):

```bash
~/MorgenCommander/MorgenCommander --save-login "youravatar" --in-file
```

## 2. Give the agent access to Morgen Commander

The agent talks to Morgen Commander with an **API token**, which says what it
may do. It's shown only once, so keep it ready for step 5.

- **Mac:** in Morgen Commander, Session → Preferences → **API**. Tick "Let
  programs and AI assistants drive avatars through MC", choose your avatar,
  press **Make a token**, and tick **Read**, **Chat**, **Answer prompts**,
  **Move**, **Log in and out**, **See inventory**, **Inventory changes** and
  **Social**. Leave **L$** off: the agent never needs money.
- **Linux:**

  ```bash
  ~/MorgenCommander/MorgenCommander --grant "youravatar" --allow login,read,chat,prompts,move,inventory_read,inventory,social
  ```

  A new `--grant` replaces the old token; `--grants` lists what's granted.

## 3. Install the agent

**Mac** (Python from [python.org](https://www.python.org/downloads/) or
Homebrew):

```bash
git clone https://github.com/sheriunderwood/mc-agent.git
cd mc-agent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Linux** (Ubuntu 24.04 or similar):

```bash
sudo apt install -y git python3 python3-venv
git clone https://github.com/sheriunderwood/mc-agent.git
cd mc-agent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

The Claude Agent SDK brings everything else it needs.

## 4. Set up your avatar's data folder

Your avatar's settings, personality and memories live in a **data folder**,
apart from the code, so you can update the code without touching them:

- **Mac:** `~/Library/Application Support/mc-agent`
- **Linux:** `~/.local/share/mc-agent`

(To use another folder, set `MCSL_HOME` to it. One data folder per avatar.)

Create it:

```bash
.venv/bin/python init.py
```

It copies in starter files and never overwrites anything, so it's safe to run
again. Then edit them, in this order:

| File | What to put in it |
|------|-------------------|
| `config.toml` | Your avatar's **name and UUID**, your **home** region, parcel and SLURL, and the names people call it by. Every setting is explained in the file. |
| `OWNERS.md` | **Your own UUID** (and any co-owners'). Only owners can give the agent orders. |
| `persona.md` | Who your avatar is and how it talks. This is where its personality comes from. |
| `RULES.md` | How it behaves. The defaults are careful; read them, and change what you'd like. |
| `FRIENDS.md` | Optional: people it already knows. It adds people itself as it meets them. |
| `CLUBS.md`, `DJS.md` | Places and DJs it may recommend. It never makes up names, so it only recommends what's listed here. |

Edits to the `.md` files take effect at the agent's next session; `config.toml`
changes when you restart it.

## 5. Store the secrets

Two secrets: the Anthropic API key and the Morgen Commander token. They never
go in the data folder, the code or a log.

**Mac:** in the Keychain (each command asks for the value, so it doesn't land
in your shell history). `mcsl-agent` is the default `[secrets] keychain_prefix`
in `config.toml`:

```bash
security add-generic-password -a "$USER" -s mcsl-agent-anthropic-key -w
security add-generic-password -a "$USER" -s mcsl-agent-mc-token -w
```

**Linux:** in `~/.config/mcsl-agent/secrets.env`, readable only by you:

```bash
mkdir -p ~/.config/mcsl-agent
nano ~/.config/mcsl-agent/secrets.env      # two lines: ANTHROPIC_API_KEY=... and MC_API_TOKEN=...
chmod 600 ~/.config/mcsl-agent/secrets.env
```

(Either way, `ANTHROPIC_API_KEY` and `MC_API_TOKEN` set in the environment win.)

## 6. Check the connection, then run it

With Morgen Commander running and your avatar logged in:

```bash
.venv/bin/python tools/check_mcp.py      # connects to Morgen Commander, no AI involved
./run.sh --observe-only --once           # one read-only look around, then stop
./run.sh --observe-only                  # watch and report, never speak or act: good for a first day
./run.sh                                 # the real thing
```

Stop it with **Ctrl-C**; it picks up where it left off. Have a friend IM your
avatar: within a few seconds it answers.

What it does goes to `logs/agent-YYYY-MM-DD.log` in the data folder, and a
daily summary to `reports/YYYY-MM-DD.md`. Things waiting for your decision are
in `APPROVALS.md`; when you come online it IMs you how many, and you can answer
by IM.

Useful options for `run.sh`: `--daily-budget 5` (dollars a day), `--observe-only`,
`--once`. `./run.sh --help` lists them all.

## 7. Run it unattended (optional)

To keep everything running on its own, including after a reboot, install it as
services: launchd on a Mac, systemd user services on Linux.

```bash
deploy/install.sh --all          # headless Morgen Commander + the agent + shopping research
deploy/install.sh --status       # what's installed and running
deploy/install.sh --uninstall    # remove them again
```

- **Headless Morgen Commander** runs without a window and logs your avatar in
  with its saved login. Quit MC's window first: the two can't run at once.
- **Keep online:** with `[mc] keep_online = true` in `config.toml`, a check
  every 5 minutes logs your avatar back in if it was dropped (not while you've
  told it to take a break). `--all` includes it.
- **Linux:** services need "lingering" to run while you're logged out. An
  admin runs once: `sudo loginctl enable-linger $USER`. Work as the avatar's
  user over SSH, not with `su`.
- Each piece on its own: `--mc`, `--agent`, `--shop`, `--online`. Arguments for
  the agent go after `--`: `deploy/install.sh --agent -- --daily-budget 5`.
- Logs: `logs/mc.log`, `logs/agent.log`, `logs/shop.log`, `logs/online.log` in
  the data folder.
- **Watching the agent on a screen:** `[log] mirror = "/dev/tty1"` in
  `config.local.toml` (this machine only) also writes each agent log line to
  that console (or any file). The avatar's user must be allowed to write to
  it; if it can't, the agent carries on without it.

## Optional: the dance HUD and the wearing HUD

Two LSL scripts the avatar can install for you (`scripts/`): a **dance HUD**
(a prim at your club that dances everyone in sync, with playlists) and a
**wearing HUD** (worn by the avatar; notes what people nearby are wearing, so
it can compliment outfits and ask where they're from). IM your avatar
"install the dance_hud script, then give it to me": it fills in your avatar's
UUID, your owners, channels and home from your config. Setup:
[scripts/README.md](scripts/README.md).

## Costs

The agent uses two Claude models: a fast, cheap one (Claude Haiku) for
everyday chat, and a more capable one (Claude Opus) for anything that needs
judgment: owners' requests, offers, trouble. It only wakes the AI when
something happens, and in a crowd it filters local chat before the AI sees it.

- **A daily cap:** `--daily-budget` (US$10 by default). Past it, only owners'
  messages, offers and trouble are handled until the next day; ordinary chat
  waits.
- `[chat] owner_model = "chat"` in `config.toml` answers owners with Haiku
  too: cheaper, a little less careful.
- **What it spent:** every AI call is logged in `usage/YYYY-MM-DD.jsonl`.
  `.venv/bin/python tools/usage_report.py --days 7` sums it up by model and by
  what woke it.

Set a spending limit in the Claude Console as well, as a backstop.

## Security

Anyone in Second Life can talk to your avatar, send it offers, or rez objects
that speak to it, and an AI can be talked into things. So the program, not
the AI, decides what's allowed:

- **Owners only for anything powerful:** teleports, accepting offers and
  permissions, wearing things, posting to groups, logging out. Only in a
  moment when an owner has just IMed, and owners are recognised **by UUID**
  from Morgen Commander's own fields, never by a name or by text in a message.
- **Narrow exceptions,** checked in code: accepting an owner's gift, a friend's
  dance invitation that only asks to animate, a friendship you approved in
  advance (`[friendship] accept_from`), a teleport offer for a friend
  (FRIENDS.md) who asks for one.
- **Deny by default:** Morgen Commander tools the agent doesn't use (paying,
  giving, updating MC, deleting…) are refused outright, even for owners.
- **Channels it never speaks on:** list a script's command channel (an RLV
  relay prim's, say) in `[chat] no_speak_channels`, and the agent is refused
  on it, typed or not, whoever asks.
- **Secrets never leave:** every message and saved note is scanned, and
  anything that looks like a key or token is refused. The AI has no shell,
  file or web access.
- **Respect:** blocked people are ignored; people who ask to be left alone are
  never contacted first again; it never starts conversations with strangers
  outside the region.
- **Privacy:** what it remembers stays in your data folder, readable only by
  you. It doesn't store real-life details people mention.

The test suite checks these rules, including attempts to get around them:

```bash
.venv/bin/python -m unittest discover -s tests
```

## Updating

```bash
git pull
.venv/bin/pip install -r requirements.txt
```

Then restart the agent: Ctrl-C and `./run.sh` again, or for the service,
`launchctl kickstart -k gui/$(id -u)/com.mcsl.<avatar>.agent` (Mac) or
`systemctl --user restart mcsl-agent` (Linux). Your data folder isn't touched;
run `init.py` again to pick up any new starter files.

## Troubleshooting

- **"No config.toml in the data folder":** run `.venv/bin/python init.py`, or
  set `MCSL_HOME` to your data folder.
- **"Morgen Commander rejected the API token":** make a new one (step 2) and
  store it again (step 5). On Linux with headless MC running, make it while
  the `mcsl-mc` service is running.
- **It doesn't answer:** is the avatar online in Morgen Commander? Look at
  `logs/agent-YYYY-MM-DD.log` in the data folder; denied actions say why.
- **"Failed to connect to bus" (Linux):** turn on lingering (step 7) and SSH
  in as the avatar's user.

## Licence

MIT: see [LICENSE](LICENSE). Morgen Commander is Morgen's, with its own terms.
