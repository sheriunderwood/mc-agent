"""First run: set up the data folder from the avatar Morgen Commander is
connected to. run.sh calls this when there's no config.toml yet.

- Makes the data folder (as init.py does) and writes config.toml from
  config.example.toml, with [avatar] name, uuid and call_names and [home]
  region, parcel and slurl filled in from MC (the avatar must be online).
- Offers the people within 10 m as owners (a numbered list, 0 for none) and
  adds the one picked to OWNERS.md. Only asks when run in a terminal.
- Then stops: start the agent again with ./run.sh.

Nothing is written unless MC answered with the avatar's name, UUID and place.
Names shown and saved come from the grid, but display names are anyone's
text: control characters and table pipes are dropped. Owners are saved by the
UUID MC gives for the person, never by name.

    MC_API_TOKEN=... .venv/bin/python first_run.py     (run.sh sets the token)
"""

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

import httpx2

import config
import init

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
OWNER_RANGE_M = 10


class Unready(Exception):
    """MC can't give what the setup needs; the message says what to do."""


def mc_caller(token: str, port: int):
    """call(command, payload) -> dict, over MC's HTTP API (as agent.mc_call)."""
    client = httpx2.Client(base_url=f"http://127.0.0.1:{port}",
                           headers={"Authorization": f"Bearer {token}"}, timeout=30)

    def call(command: str, payload: dict | None = None) -> dict:
        try:
            r = client.post(f"/api/call/{command}", json=payload or {})
        except (httpx2.HTTPError, OSError) as e:
            raise Unready(f"Can't reach Morgen Commander on port {port} ({type(e).__name__}). Is it "
                          f"running, with Preferences → API turned on?")
        if r.status_code in (401, 403):
            raise Unready("Morgen Commander rejected the API token. Make one with MorgenCommander "
                          "--grant \"<avatar>\" while MC is running (see DEPLOY.md).")
        try:
            data = r.json()
        except ValueError:
            data = None
        return data if isinstance(data, dict) else {"ok": False}
    return call


def clean(text, limit: int = 64) -> str:
    """Grid text made safe to print and to put in a Markdown table cell."""
    text = re.sub(r"[\x00-\x1f\x7f-\x9f|`​-‏‪-‮⁦-⁩]", "", str(text or ""))
    return " ".join(text.split())[:limit]


def uuid_of(value) -> str | None:
    value = str(value or "").strip().lower()
    return value if UUID_RE.fullmatch(value) else None


def same_name(a: str, b: str) -> bool:
    """Account names match: "first.last" = "First Last", "first" = "First Resident"."""
    def norm(n: str) -> str:
        n = re.sub(r"[\s.]+", " ", str(n or "").strip().lower())
        return n[:-len(" resident")] if n.endswith(" resident") else n
    return bool(norm(a)) and norm(a) == norm(b)


def people_in(result: dict) -> list[dict]:
    for key in ("people", "results", "matches", "found"):
        if isinstance(result.get(key), list):
            return [p for p in result[key] if isinstance(p, dict)]
    return []


def own_uuid(call, status: dict, name: str) -> str | None:
    """The avatar's UUID: from status if MC gives it there, else the grid's
    exact match for its account name."""
    for key in ("uuid", "id", "avatar_id", "agent_id"):
        if uuid := uuid_of(status.get(key)):
            return uuid
    found = call("find_person", {"name": name, "max": 50})
    matches = {uuid_of(p.get("id") or p.get("uuid")) for p in people_in(found)
               if any(same_name(name, p.get(k)) for k in ("name", "username", "account", "legacy_name"))}
    matches.discard(None)
    return matches.pop() if len(matches) == 1 else None


def slurl_for(status: dict) -> str:
    if str(status.get("slurl") or "").startswith("https://maps.secondlife.com/secondlife/"):
        return str(status["slurl"])
    pos = status.get("position")
    try:
        x, y, z = (round(float(pos[k])) for k in ("x", "y", "z"))
    except (TypeError, KeyError, ValueError):
        return ""
    return f"https://maps.secondlife.com/secondlife/{quote(str(status['region']))}/{x}/{y}/{z}"


def avatar_facts(call) -> dict:
    """name, uuid, region, parcel, slurl of the online avatar, or Unready."""
    status = call("status")
    name = str(status.get("avatar") or "").strip()
    if not status.get("ok", True) or not name:
        raise Unready("Morgen Commander didn't say which avatar it's connected to.")
    if not status.get("online"):
        raise Unready(f"{clean(name)} is offline. Log them in in Morgen Commander, then run ./run.sh again.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,62}", name):
        raise Unready("Morgen Commander gave an avatar name that doesn't look like an account name.")
    region, parcel = clean(status.get("region")), clean(status.get("parcel"), 120)
    if not region:
        raise Unready(f"Morgen Commander didn't say where {name} is. Wait until they've arrived, then try again.")
    uuid = own_uuid(call, status, name)
    if not uuid:
        raise Unready(f"Couldn't find {name}'s UUID (status and find_person didn't give one).")
    return {"name": name, "uuid": uuid, "region": region, "parcel": parcel, "slurl": slurl_for(status)}


def candidates(nearby: dict, self_uuid: str) -> list[dict]:
    """People within OWNER_RANGE_M, nearest first, by the UUID MC gives."""
    out = []
    for p in people_in(nearby):
        uuid, d = uuid_of(p.get("id") or p.get("uuid")), p.get("distance")
        if not uuid or uuid == self_uuid or isinstance(d, bool) or not isinstance(d, (int, float)) \
                or not 0 <= d <= OWNER_RANGE_M:
            continue
        account = clean(p.get("name") or p.get("username"))
        display = clean(p.get("display") or p.get("display_name"))
        if not account:
            continue
        label = f"{display} ({account})" if display and display.lower() != account.lower() else account
        out.append({"uuid": uuid, "label": label, "distance": float(d)})
    return sorted(out, key=lambda c: c["distance"])


def set_value(text: str, section: str, key: str, value: str) -> str:
    """text with `key = ...` in [section] set to value (a TOML basic string),
    keeping any comment after it. The key must be there exactly once."""
    head = re.search(rf"^\[{re.escape(section)}\][ \t]*$", text, re.M)
    if not head:
        raise ValueError(f"no [{section}] in config.example.toml")
    end = re.search(r"^\[", text[head.end():], re.M)
    body_end = head.end() + (end.start() if end else len(text) - head.end())
    body = text[head.end():body_end]
    line = re.compile(rf"""^({re.escape(key)}[ \t]*=[ \t]*)("(?:[^"\\\n]|\\.)*"|'[^'\n]*')""", re.M)
    if len(line.findall(body)) != 1:
        raise ValueError(f"{key} isn't in [{section}] exactly once in config.example.toml")
    body = line.sub(lambda m: m.group(1) + json.dumps(value), body)
    return text[:head.end()] + body + text[body_end:]


def config_text(example: str, facts: dict) -> str:
    first = re.split(r"[\s.]+", facts["name"])[0].lower()
    text = example
    for section, key, value in (("avatar", "name", facts["name"]), ("avatar", "uuid", facts["uuid"]),
                                ("avatar", "call_names", rf"\b{re.escape(first)}\b"),
                                ("home", "region", facts["region"]), ("home", "parcel", facts["parcel"]),
                                ("home", "slurl", facts["slurl"])):
        text = set_value(text, section, key, value)
    return text


def ask_owner(people: list[dict], ask=input, say=print) -> dict | None:
    """The operator's pick from the numbered list, or None for 0 / end of input."""
    say("\nWho owns this avatar? Owners can give it orders by IM. People within "
        f"{OWNER_RANGE_M} m:")
    for i, p in enumerate(people, 1):
        say(f"  {i}. {p['label']}  ({p['distance']:.1f} m)")
    say("  0. None of them")
    while True:
        try:
            answer = ask(f"Number (0-{len(people)}): ").strip()
        except EOFError:
            return None
        if answer.isdigit() and int(answer) <= len(people):
            return people[int(answer) - 1] if int(answer) else None
        say(f"Please type a number from 0 to {len(people)}.")


def add_owner(owners: Path, person: dict) -> bool:
    """Add a row for person to OWNERS.md's table; False if they're already in it."""
    text = owners.read_text() if owners.exists() else "| UUID | Name | Notes |\n|------|------|-------|\n"
    if person["uuid"] in text.lower():
        return False
    name = clean(re.sub(UUID_RE.pattern, "", person["label"], flags=re.I), 120)   # only the first cell's UUID counts
    row = f"| {person['uuid']} | {name} | added by first_run.py |\n"
    owners.write_text(text + ("" if text.endswith("\n") else "\n") + row)
    return True


def setup(target: Path, call, interactive: bool, ask=input, say=print) -> int:
    if (target / "config.toml").exists():
        say(f"{target / 'config.toml'} already exists: nothing to set up.")
        return 0
    try:
        facts = avatar_facts(call)
        people = candidates(call("nearby"), facts["uuid"])
    except Unready as e:
        say(f"Can't set up yet: {e}\nNothing was written.")
        return 1
    text = config_text((init.CODE / "config.example.toml").read_text(), facts)
    init.make_folder(target)
    (target / "config.toml").write_text(text)
    say(f"Set up the data folder {target} for {facts['name']} ({facts['uuid']}),\n"
        f"home: {facts['region']}" + (f", {facts['parcel']}" if facts["parcel"] else "")
        + (f"\n  {facts['slurl']}" if facts["slurl"] else ""))

    if not people:
        say(f"\nNo one is within {OWNER_RANGE_M} m to make an owner. Add owners to "
            f"{target / 'OWNERS.md'} yourself (UUID, name).")
    elif not interactive:
        say(f"\nNot run in a terminal, so no owner was asked for. Add owners to "
            f"{target / 'OWNERS.md'} yourself, or delete config.toml and run ./run.sh in a terminal.")
    elif owner := ask_owner(people, ask, say):
        added = add_owner(target / "OWNERS.md", owner)
        say(f"{'Added' if added else 'Already listed:'} {owner['label']} ({owner['uuid']}) "
            f"{'to' if added else 'in'} OWNERS.md.")
    else:
        say(f"No owner added. Add owners to {target / 'OWNERS.md'} yourself before giving it orders.")
    say("\nCheck config.toml, persona.md and RULES.md there, then start the agent again: ./run.sh")
    return 0


def main() -> int:
    target = config.DATA_DIR
    if init.inside_code(target):
        print(f"The data folder can't be inside the code folder ({init.CODE}). Set MCSL_HOME to another one.")
        return 1
    token = os.environ.get("MC_API_TOKEN") or config.secret("MC_API_TOKEN")
    if not token:
        print("No MC_API_TOKEN: start it with ./run.sh, which finds the token.")
        return 1
    call = mc_caller(token, int(os.environ.get("MC_API_PORT", "47174")))
    return setup(target, call, interactive=sys.stdin.isatty() and sys.stdout.isatty())


if __name__ == "__main__":
    sys.exit(main())
