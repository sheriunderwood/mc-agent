"""Set up a data folder for the agent: one avatar's config, persona, rules,
owners and friends, plus the folders the agent writes to.

    .venv/bin/python init.py              the data folder config.py finds (see below)
    .venv/bin/python init.py DIR          a folder of your choice; then set MCSL_HOME=DIR
                                          for the agent (install.sh passes it to the services)

The data folder is $MCSL_HOME, else ~/Library/Application Support/mc-agent on
macOS, ~/.local/share/mc-agent on Linux. It copies in config.example.toml (as
config.toml) and the starter files from templates/, and never overwrites a
file that's already there, so running it again is safe: it only adds what's
missing. Then edit the files it lists.
"""

import os
import shutil
import sys
from pathlib import Path

import config

CODE = config.CODE_DIR
TEMPLATES = CODE / "templates"
FOLDERS = ("logs", "friends", "reports", "usage", "shopping", "wearing", "scripts", "extensions")


def main() -> int:
    target = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else config.DATA_DIR
    if target == CODE or CODE in target.parents:
        print(f"Not inside the code folder ({CODE}): your data is kept apart from the code, "
              f"so you can update or share the code without it. Pick another folder.")
        return 1
    new = not target.exists()
    target.mkdir(parents=True, exist_ok=True)
    os.chmod(target, 0o700)                 # friends' notes and reports are private
    for name in FOLDERS:
        (target / name).mkdir(exist_ok=True)

    copies = [(CODE / "config.example.toml", target / "config.toml")]
    if TEMPLATES.is_dir():
        copies += [(src, target / src.relative_to(TEMPLATES))
                   for src in sorted(TEMPLATES.rglob("*")) if src.is_file()]
    added, kept = [], []
    for src, dst in copies:
        if dst.exists():
            kept.append(dst.relative_to(target))
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        added.append(dst.relative_to(target))

    print(f"{'Made' if new else 'Checked'} the data folder: {target}")
    for p in added:
        print(f"  added {p}")
    if kept:
        print(f"  kept {len(kept)} file(s) already there (never overwritten)")
    if target != config.DATA_DIR:
        print(f"\nThe agent looks in {config.DATA_DIR} unless told otherwise. Point it here with:\n"
              f"  export MCSL_HOME=\"{target}\"\n"
              f"(deploy/install.sh then passes it to the services.)")
    print("\nNext, edit these in the data folder:\n"
          "  config.toml   your avatar's name and UUID, home region and parcel, keychain prefix\n"
          "  OWNERS.md     your own UUID: only owners can give the agent orders\n"
          "  persona.md    who the avatar is and how it talks\n"
          "  RULES.md      how it behaves (read it: the defaults are careful)\n"
          "Then add the secrets (README: \"Secrets\") and check the connection to\n"
          "Morgen Commander: .venv/bin/python tools/check_mcp.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
