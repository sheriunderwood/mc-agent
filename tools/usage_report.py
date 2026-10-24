"""Where the avatar's AI spend goes, from the usage log (usage/YYYY-MM-DD.jsonl,
one line per tick, written by agent.py).

    .venv/bin/python tools/usage_report.py              # today
    .venv/bin/python tools/usage_report.py 2026-10-18   # one day
    .venv/bin/python tools/usage_report.py --days 7     # the last 7 days

Shows spend by model tier, by what woke the agent (kind, and why the smart model
was used), how big the prompts got (Haiku costs 5x more past 100k tokens), and
the most expensive ticks.
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config                              # noqa: E402

USAGE_DIR = config.DATA_DIR / "usage"
HAIKU_CLIFF = 100_000


def load(days: list[date]) -> list[dict]:
    rows = []
    for d in days:
        path = USAGE_DIR / f"{d}.jsonl"
        if path.exists():
            for line in path.read_text().splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def table(title: str, groups: dict[str, list[dict]], total: float) -> None:
    print(f"\n{title}")
    print(f"  {'':28} {'ticks':>6} {'cost':>9} {'share':>6} {'avg':>8}")
    for name, rows in sorted(groups.items(), key=lambda kv: -sum(r.get("cost", 0) for r in kv[1])):
        cost = sum(r.get("cost", 0) for r in rows)
        share = f"{100 * cost / total:.0f}%" if total else "-"
        print(f"  {name[:28]:28} {len(rows):6} ${cost:8.3f} {share:>6} ${cost / len(rows):7.4f}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("day", nargs="?", help="YYYY-MM-DD (default: today)")
    p.add_argument("--days", type=int, help="the last N days instead of one day")
    a = p.parse_args()
    if a.days:
        days = [date.today() - timedelta(days=i) for i in range(a.days - 1, -1, -1)]
    else:
        days = [date.fromisoformat(a.day) if a.day else date.today()]
    rows = load(days)
    span = f"{days[0]}" + (f" to {days[-1]}" if len(days) > 1 else "")
    if not rows:
        print(f"No usage records for {span} (usage/ starts with the build that added it).")
        return
    total = sum(r.get("cost", 0) for r in rows)
    print(f"{config.AVATAR or 'Agent'} AI spend, {span}: ${total:.2f} over {len(rows)} ticks")

    table("By model tier", group(rows, lambda r: f"{r.get('backend')} ({short_model(r.get('model'))})"), total)
    table("By what woke the agent", group(rows, lambda r: r.get("kind") or "?"), total)
    smart = [r for r in rows if r.get("backend") == "smart"]
    if smart:
        table("Smart model: why", group(smart, lambda r: r.get("why") or "?"), sum(r.get("cost", 0) for r in smart))
    owner = [r for r in rows if r.get("why") == "owner"]
    if owner:
        # [chat] owner_model in config.toml; an escalated chat tick also ran again on the smart model
        table("Owner messages: which model", group(owner, lambda r: f"{r.get('backend')}"
                                                   + (" (escalated)" if r.get("escalated") else "")),
              sum(r.get("cost", 0) for r in owner))

    ticks = [r for r in rows if r.get("backend") not in ("qa",) and r.get("max_context")]
    if ticks:
        print("\nPrompt size (the largest single API call in a tick)")
        for backend, rs in sorted(group(ticks, lambda r: r.get("backend")).items()):
            ctx = sorted(r["max_context"] for r in rs)
            over = sum(1 for c in ctx if c > HAIKU_CLIFF)
            print(f"  {backend:8} median {ctx[len(ctx) // 2]:>7,}  max {ctx[-1]:>7,}  "
                  f"over 100k: {over} of {len(ctx)}")
        by_tick = group([r for r in ticks if r.get("session_tick")], lambda r: r["session_tick"])
        if len(by_tick) > 1:
            print("  by tick number within a session (history grows):")
            for n in sorted(by_tick, key=int):
                rs = by_tick[n]
                print(f"    tick {int(n):2}: avg prompt {sum(r['max_context'] for r in rs) // len(rs):>7,}, "
                      f"avg cost ${sum(r.get('cost', 0) for r in rs) / len(rs):.4f} ({len(rs)} ticks)")
        reads = sum(r.get("cache_read", 0) for r in ticks)
        fresh = sum(r.get("input", 0) + r.get("cache_write", 0) for r in ticks)
        if reads + fresh:
            print(f"  prompt caching: {100 * reads / (reads + fresh):.0f}% of input tokens were cache reads")

    print("\nMost expensive ticks")
    for r in sorted(rows, key=lambda r: -r.get("cost", 0))[:8]:
        print(f"  {r.get('time', '?')}  ${r.get('cost', 0):.3f}  {r.get('backend')}/{r.get('kind')}"
              f"  {r.get('why') or ''}  turns {r.get('turns', '-')}  prompt {r.get('max_context', 0):,}")


def group(rows, key) -> dict[str, list[dict]]:
    out = defaultdict(list)
    for r in rows:
        out[str(key(r))].append(r)
    return out


def short_model(m) -> str:
    return str(m or "?").removeprefix("claude-")


if __name__ == "__main__":
    main()
