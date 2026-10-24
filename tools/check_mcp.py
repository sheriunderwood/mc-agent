#!/usr/bin/env python3
"""Check the Morgen Commander MCP connection without any AI model.

Starts `MorgenCommander --mcp` exactly as the agent does, lists its tools, and
calls `status`. If this works, MC's side is fine and any problem is with the
model or the agent. If it fails, the problem is the MC connection.

  MC_API_TOKEN=... .venv/bin/python tools/check_mcp.py    (or: ./run.sh is not needed;
  the token can also come from the Keychain, see below)
"""

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import config                              # noqa: E402
MC = config.MC_COMMAND
SERVICE = f"{config.KEYCHAIN_PREFIX}-mc-token"


def token() -> str:
    tok = config.secret("MC_API_TOKEN")
    if not tok:
        sys.exit(f"No MC_API_TOKEN in the environment, {config.SECRETS_FILE}, or the Keychain ({SERVICE}).")
    return tok


def main() -> None:
    env = dict(os.environ, MC_API_TOKEN=token())
    print(f"starting: {MC} --mcp")
    p = subprocess.Popen([MC, "--mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, env=env)

    def call(i: int, method: str, params: dict) -> dict:
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n")
        p.stdin.flush()
        start = time.time()
        while time.time() - start < 30:
            line = p.stdout.readline()
            if not line:
                err = p.stderr.read()
                sys.exit(f"FAILED: MorgenCommander --mcp exited.\n{err.strip()}")
            msg = json.loads(line)
            if msg.get("id") == i:
                return msg
        sys.exit(f"FAILED: no answer to {method} within 30 s")

    init = call(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                  "clientInfo": {"name": "check_mcp", "version": "1"}})
    if "error" in init:
        sys.exit(f"FAILED at initialize: {init['error']}")
    print("initialize: ok,", init["result"].get("serverInfo"))
    p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    p.stdin.flush()

    tools = call(2, "tools/list", {})
    if "error" in tools:
        sys.exit(f"FAILED at tools/list: {tools['error']}")
    names = [t["name"] for t in tools["result"]["tools"]]
    print(f"tools/list: {len(names)} tools: {', '.join(names)}")
    for needed in ("events", "send", "say", "status"):
        if needed not in names:
            print(f"  WARNING: '{needed}' is missing; check the token's permissions in MC")

    status = call(3, "tools/call", {"name": "status", "arguments": {}})
    if "error" in status:
        sys.exit(f"FAILED at status: {status['error']}")
    text = " ".join(c.get("text", "") for c in status["result"].get("content", []))
    print("status:", text[:400])
    p.terminate()
    print("\nOK: Morgen Commander's MCP connection works.")


if __name__ == "__main__":
    main()
