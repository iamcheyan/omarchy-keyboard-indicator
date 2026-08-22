#!/usr/bin/env python3
"""Runtime CapsLock <-> Left Ctrl swap for Omarchy.

Applies the standard XKB option ``ctrl:swapcaps`` through the Lua bridge
(``hyprctl eval 'hl.config({ input = { kb_options = ... } })'``) so nothing
is ever written to the user's Hyprland configuration. Toggling off restores
the previous option list exactly as it was found.

Commands:
    status   print a JSON snapshot: {"enabled": bool, "options": str}
    enable   add ctrl:swapcaps to the current options
    disable  remove ctrl:swapcaps from the current options
    ensure   re-apply if the persisted intent says enabled (used after
             Hyprland/shell restarts, where runtime changes are lost)
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

OPTION = "ctrl:swapcaps"
KEY = "input:kb_options"
STATE_DIR = pathlib.Path(
    os.environ.get("XDG_STATE_HOME", pathlib.Path.home() / ".local/state")
) / "hancore.ctrl-swap"
STATE_FILE = STATE_DIR / "enabled"


def set_options(value: str) -> None:
    # Omarchy Quattro's Hyprland disables `hyprctl keyword` ("non-legacy
    # parsers"); runtime settings go through the Lua bridge instead.
    safe = value.replace('\\', '\\\\').replace('"', '\\"')
    lua = f'hl.config({{ input = {{ kb_options = "{safe}" }} }})'
    subprocess.run(["hyprctl", "eval", lua], check=False)


def run(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True)
    return result.stdout.strip()


def current_options() -> str:
    raw = run("hyprctl", "-j", "getoption", KEY)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    value = data.get("str", "")
    return value if isinstance(value, str) else ""




def is_enabled(options: str) -> bool:
    return OPTION in [part.strip() for part in options.split(",")]


def enable() -> None:
    options = current_options()
    if is_enabled(options):
        persist(True)
        return
    parts = [part.strip() for part in options.split(",") if part.strip()]
    parts.append(OPTION)
    set_options(",".join(parts))
    persist(True)


def disable() -> None:
    options = current_options()
    parts = [part.strip() for part in options.split(",") if part.strip() and part.strip() != OPTION]
    set_options(",".join(parts))
    persist(False)


def ensure() -> None:
    """Re-apply after a Hyprland reload/restart if the user left it on."""
    if STATE_FILE.exists() and not is_enabled(current_options()):
        enable()


def persist(on: bool) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if on:
        STATE_FILE.write_text("1\n")
    else:
        STATE_FILE.unlink(missing_ok=True)


def status() -> None:
    options = current_options()
    print(json.dumps({"enabled": is_enabled(options), "options": options}))


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    actions = {"status": status, "enable": enable, "disable": disable, "ensure": ensure}
    action = actions.get(command)
    if action is None:
        print(f"unknown command: {command}", file=sys.stderr)
        return 2
    action()
    return 0


if __name__ == "__main__":
    sys.exit(main())
