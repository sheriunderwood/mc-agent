#!/usr/bin/env python3
"""Shopping list research for the avatar.

For each store: find it on the Second Life Marketplace, read its store page for
the owner and the in-world location (SLURL), and check that the SLURL's region
still exists on the grid. Results go in shopping/<category>.md.

  shop_lookup.py add "Store Name" --category hair --source "the owner's profile"
  shop_lookup.py inbox     # research everything the agent noted in shopping/inbox.md
  shop_lookup.py verify    # re-check every SLURL in shopping/*.md and CLUBS.md
  shop_lookup.py due       # what's due: the inbox now, and verify once a day after 4 am
                           # (run every 15 minutes by deploy/install.sh --shop)
  shop_lookup.py visits    # stores the owner should visit (never visited, gone, or stale)
  shop_lookup.py visited "Store" --result ok|gone|moved [--slurl Region/x/y/z] [--note ...]

Two kinds of checking:
- Region check (automatic): the region in the SLURL still exists on the grid,
  per the official map API. It can't tell whether the store is still there.
- Owner visited (by hand): the avatar's owner went to the SLURL and saw the
  store, or saw that it's gone or has moved. Re-visit after VISIT_STALE_DAYS.
"""

import argparse
import contextlib
import html
import io
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config                              # noqa: E402

ROOT = config.DATA_DIR
SHOP = ROOT / "shopping"
INBOX = SHOP / "inbox.md"
CATEGORIES = ["clothing", "skins", "hair", "shoes", "jewelry", "animations", "gestures",
              "tattoos-makeup", "accessories", "other"]
MARKET = "https://marketplace.secondlife.com"
MAP_API = "https://cap.secondlife.com/cap/0/d661249b-2b5a-4436-966a-3d3b8d7a574f"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
SLURL_RE = re.compile(r"(?:maps\.secondlife\.com|slurl\.com)/secondlife/([^/\"'<>\s]+)/(\d+)/(\d+)/(\d+)")
HEADER = ("| Store | Marketplace | In-world | Region check | Owner visited | Marketplace categories | Heard about from |\n"
          "|-------|-------------|----------|--------------|---------------|------------------------|------------------|\n")
# Column positions in " | "-split rows (cell 0 includes the leading "| ").
STORE, MARKET_COL, INWORLD, REGION, VISITED, CATS, SOURCE = range(7)
VISIT_STALE_DAYS = 90

_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
_opener.addheaders = [("User-Agent", UA)]


def fetch(url: str) -> str:
    for attempt in range(3):
        try:
            with _opener.open(url, timeout=30) as r:
                return r.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(3)
    return ""


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def region_exists(region: str) -> bool | None:
    """True/False from the map API, or None if it couldn't be reached or gave an
    answer that is neither coordinates nor "no such region" (since 2026-10 it
    answers "Invalid Capability ID." to everything; that isn't "gone")."""
    try:
        body = fetch(f"{MAP_API}?var=coords&sim_name={urllib.parse.quote(region)}")
    except (urllib.error.URLError, TimeoutError):
        return None
    if "'x'" in body:
        return True
    if "'error'" in body:
        return False
    return None


def lookup(name: str) -> dict:
    """Marketplace store, owner, in-world SLURL and categories for a store name."""
    out = {"name": name}
    q = urllib.parse.urlencode({"search[keywords]": name})
    page = fetch(f"{MARKET}/products/search?{q}")
    # Each product in the results names its store. Only take a store whose name
    # matches what we searched for: the top hit is often a reseller.
    found = re.findall(r'href="/stores/(\d+)">\s*<span class="store-item">\s*([^<]+?)\s*</span>', page)
    names = {sid: html.unescape(n) for sid, n in found}
    counts = Counter(sid for sid, _ in found)
    matching = [sid for sid, _ in counts.most_common()
                if norm(name) and norm(names[sid])
                and (norm(name) in norm(names[sid]) or norm(names[sid]) in norm(name))]
    if not matching:
        others = [names[sid] for sid, _ in counts.most_common(3)]
        if others:
            out["note"] = "only other stores matched (resellers?): " + ", ".join(others)
        return out
    store_id = matching[0]
    sp = fetch(f"{MARKET}/stores/{store_id}")
    title = html.unescape(re.search(r"<title>([^<]*)", sp).group(1)) if "<title>" in sp else ""
    m = re.match(r"Second Life Marketplace - (.*?)(?: by (.*))?$", title.strip())
    store_name, owner = (m.group(1), m.group(2) or "") if m else (name, "")
    out.update(store_id=store_id, store_name=store_name, owner=owner,
               url=f"{MARKET}/stores/{store_id}",
               name_matches=bool(norm(store_name)) and (norm(name) in norm(store_name)
                                                        or norm(store_name) in norm(name)))
    if s := SLURL_RE.search(sp):
        region = urllib.parse.unquote(s.group(1)).replace("+", " ")
        out["slurl"] = (region, *s.group(2, 3, 4))
    cats = re.findall(r">\s*([A-Z][A-Za-z &]{2,40}?)\s*(?:<[^>]+>\s*)*<span[^>]*category-count[^>]*>(\d+)<", sp)
    out["categories"] = ", ".join(f"{c.strip()} ({n})" for c, n in cats[:4])
    return out


def slurl_cell(region: str, x, y, z) -> str:
    return f"[{region}/{x}/{y}/{z}](https://maps.secondlife.com/secondlife/{urllib.parse.quote(region)}/{x}/{y}/{z})"


def verified_cell(region: str | None) -> str:
    if not region:
        return "—"
    ok = region_exists(region)
    return {True: f"✓ region up {date.today()}", False: f"✗ region gone {date.today()}",
            None: "? map API not answering"}[ok]


def row_for(info: dict, source: str) -> str:
    name = info.get("store_name") or info["name"]
    if info.get("owner"):
        name += f" (by {info['owner']})"
    if info.get("store_id") and not info.get("name_matches"):
        name += f" ⚠ searched for “{info['name']}”, check this is the right store"
    market = (f"[store #{info['store_id']}]({info['url']})" if info.get("store_id")
              else "not found" + (f" ({info['note']})" if info.get("note") else ""))
    if info.get("slurl"):
        region = info["slurl"][0]
        inworld, verified = slurl_cell(*info["slurl"]), verified_cell(region)
    else:
        inworld, verified = "not listed", "—"
    cats = info.get("categories") or "—"
    return f"| {name} | {market} | {inworld} | {verified} | — | {cats} | {source} |"


def category_file(category: str) -> Path:
    path = SHOP / f"{category}.md"
    if not path.exists():
        SHOP.mkdir(exist_ok=True)
        path.write_text(f"# {category.replace('-', ' & ').title()}\n\n{HEADER}")
    return path


def already_listed(name: str) -> Path | None:
    for path in SHOP.glob("*.md"):
        if path.name == "inbox.md":
            continue
        for line in path.read_text().splitlines():
            if line.startswith("| ") and norm(name) and norm(name) in norm(line.split("|")[1]):
                return path
    return None


def add(name: str, category: str, source: str) -> str:
    if category not in CATEGORIES:
        raise SystemExit(f"Category must be one of: {', '.join(CATEGORIES)}")
    if where := already_listed(name):
        return f"{name}: already in {where.name}"
    info = lookup(name)
    path = category_file(category)
    text = path.read_text().rstrip("\n") + "\n" + row_for(info, source) + "\n"
    path.write_text(text)
    return f"{name}: added to {path.name} ({'found' if info.get('store_id') else 'not found'} on Marketplace)"


def process_inbox() -> None:
    """Lines in shopping/inbox.md: '- [ ] Store name | category | source'."""
    if not INBOX.exists():
        return
    lines = INBOX.read_text().splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"- \[ \] (.+?) \| ([a-z\-]+) \| (.*)", line)
        if not m:
            continue
        name, category, source = m.groups()
        if category not in CATEGORIES:
            category = "other"
        try:
            result = add(name.strip(), category, source.strip())
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"{name}: lookup failed ({e}); will retry")
            continue
        print(result)
        lines[i] = line.replace("- [ ]", "- [x]", 1) + f" — researched {date.today()}"
        INBOX.write_text("\n".join(lines) + "\n")
        time.sleep(2)   # be gentle with the Marketplace


def verify_all() -> None:
    """Re-check the region of every SLURL in shopping/*.md (Verified column)
    and report on CLUBS.md."""
    for path in sorted(SHOP.glob("*.md")):
        if path.name == "inbox.md":
            continue
        lines, changed = path.read_text().splitlines(), False
        for i, line in enumerate(lines):
            cells = line.split(" | ")
            if not line.startswith("| ") or len(cells) < 7 or not (s := SLURL_RE.search(cells[INWORLD])):
                continue
            region = urllib.parse.unquote(s.group(1)).replace("+", " ")
            cell = verified_cell(region)
            if cell.startswith("?") and cells[REGION].strip() not in ("", "—"):
                print(f"{path.name}: {cells[STORE].strip('| ')[:40]} → {cell}; kept {cells[REGION]}")
                continue   # an unanswered check never overwrites a real result
            cells[REGION] = cell
            lines[i], changed = " | ".join(cells), True
            print(f"{path.name}: {cells[STORE].strip('| ')[:40]} → {cells[REGION]}")
            time.sleep(1)
        if changed:
            path.write_text("\n".join(lines) + "\n")
    clubs = ROOT / "CLUBS.md"
    if clubs.exists():
        for s in SLURL_RE.finditer(clubs.read_text()):
            region = urllib.parse.unquote(s.group(1)).replace("+", " ")
            print(f"CLUBS.md: {region} → {verified_cell(region)}")


VERIFIED_FILE = ROOT / "logs" / "shop-verified"   # the day of the last full verify (this machine)
VERIFY_HOUR = 4                                    # verify once a day, at the first run after 4 am


def run_due() -> None:
    """The shopping chores that are due, logged with timestamps: research the
    inbox, and once a day re-check every SLURL (reporting only the bad news)."""
    def say(text: str) -> None:
        print(f"{datetime.now():%Y-%m-%d %H:%M:%S} shop: {text}", flush=True)

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        process_inbox()
    for line in out.getvalue().splitlines():
        say(line)
    today = str(date.today())
    last = VERIFIED_FILE.read_text().strip() if VERIFIED_FILE.exists() else ""
    if datetime.now().hour >= VERIFY_HOUR and last != today:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            verify_all()
        bad = [l for l in out.getvalue().splitlines() if re.search(r"gone|unreachable", l)]
        for line in bad:
            say(f"verify: {line}")
        VERIFIED_FILE.parent.mkdir(exist_ok=True)
        VERIFIED_FILE.write_text(today + "\n")
        say(f"verified every SLURL ({len(bad)} problem(s))")


def store_rows():
    """(path, line index, cells) for every store row in the category lists."""
    for path in sorted(SHOP.glob("*.md")):
        if path.name == "inbox.md":
            continue
        for i, line in enumerate(path.read_text().splitlines()):
            if line.startswith("| ") and not line.startswith("| Store |"):
                cells = line.split(" | ")
                if len(cells) >= 7:
                    yield path, i, cells


def needs_visit() -> list[dict]:
    """Stores worth asking the owner to visit, most useful first: region gone,
    never visited, then visits older than VISIT_STALE_DAYS. Only stores with an
    in-world SLURL (or that were found gone) are listed."""
    out = []
    for path, _, cells in store_rows():
        slurl = SLURL_RE.search(cells[INWORLD])
        visited, region = cells[VISITED], cells[REGION]
        store = cells[STORE].strip("| ")
        when = re.search(r"(\d{4}-\d{2}-\d{2})", visited)
        if not slurl:
            continue
        link = "https://maps.secondlife.com/secondlife/" + "/".join(slurl.groups())
        if "✗" in region:
            reason, rank = "region seems gone: is the store somewhere else now?", 0
        elif visited.strip() in ("—", ""):
            reason, rank = "never visited", 1
        elif when and (date.today() - date.fromisoformat(when.group(1))).days > VISIT_STALE_DAYS:
            reason, rank = f"last visited {when.group(1)}", 2
        else:
            continue
        out.append({"rank": rank, "category": path.stem, "store": store, "slurl": link, "reason": reason})
    return sorted(out, key=lambda d: d["rank"])


def record_visit(store: str, result: str, slurl: str = "", note: str = "") -> str:
    """Record what the owner found. result: ok (store is there), gone (no store there),
    or moved (it's at slurl now)."""
    if result not in ("ok", "gone", "moved"):
        raise ValueError("result must be ok, gone or moved")
    key = norm(store)
    for path, i, cells in store_rows():
        if not key or key not in norm(cells[STORE]):
            continue
        today = date.today()
        if result == "moved":
            m = SLURL_RE.search(slurl) or re.match(r"([^/]+)/(\d+)/(\d+)/(\d+)$", slurl.strip())
            if not m:
                raise ValueError("moved needs the new SLURL, e.g. Region/128/128/25")
            region = urllib.parse.unquote(m.group(1)).replace("+", " ")
            cells[INWORLD] = slurl_cell(region, *m.group(2, 3, 4))
            cells[REGION] = verified_cell(region)
        where = SLURL_RE.search(cells[INWORLD])
        place = urllib.parse.unquote("/".join(where.groups())) if where else "?"
        cells[VISITED] = {"ok": f"✓ store there, at {place}, {today}",
                          "gone": f"✗ no store at {place}, {today}",
                          "moved": f"✓ moved; found at {place}, {today}"}[result]
        if note:
            cells[VISITED] += " (" + " ".join(note.split())[:120].replace("|", "/") + ")"
        lines = path.read_text().splitlines()
        lines[i] = " | ".join(cells)
        path.write_text("\n".join(lines) + "\n")
        return f"{cells[STORE].strip('| ')}: {cells[VISITED]}"
    raise ValueError(f"no store matching {store!r} in the lists")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("name")
    a.add_argument("--category", required=True, choices=CATEGORIES)
    a.add_argument("--source", default="")
    sub.add_parser("inbox")
    sub.add_parser("verify")
    sub.add_parser("due")
    sub.add_parser("visits")
    v = sub.add_parser("visited")
    v.add_argument("store")
    v.add_argument("--result", required=True, choices=["ok", "gone", "moved"])
    v.add_argument("--slurl", default="")
    v.add_argument("--note", default="")
    args = p.parse_args()
    if args.cmd == "visits":
        for d in needs_visit():
            print(f"{d['category']:15} {d['store'][:40]:40} {d['slurl']}  ({d['reason']})")
    elif args.cmd == "visited":
        print(record_visit(args.store, args.result, args.slurl, args.note))
    elif args.cmd == "add":
        print(add(args.name, args.category, args.source))
    elif args.cmd == "inbox":
        process_inbox()
    elif args.cmd == "due":
        run_due()
    else:
        verify_all()
    sys.exit(0)
