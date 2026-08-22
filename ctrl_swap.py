#!/usr/bin/env python3
"""CapsLock <-> Left Ctrl remapping and CapsLock-position Voxtype for Omarchy using keyd."""

from __future__ import annotations

import base64
import fcntl
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

STATE_DIR = pathlib.Path(
    os.environ.get("XDG_STATE_HOME", pathlib.Path.home() / ".local/state")
) / "hancore.keyboard-center"
STATE_FILE = STATE_DIR / "enabled"
KEYD_DEST = pathlib.Path("/etc/keyd/hancore-ctrl-swap.conf")
KEYD_REPOSITORY = "https://github.com/rvaiya/keyd.git"
# Pin the source that is compiled and installed through pkexec.  The commit
# hash is the integrity check: a moving branch must never reach the root
# command that builds keyd.
KEYD_COMMIT = "f564288ac2b19d2305a5b39023c474805ff8fce5"
CONFIG_SCHEMA = "hancore keyboard-center four-state/2"
VOICE_STATE_FILE = STATE_DIR / "voice_enabled"
VOICE_DESCRIPTION = "CapsLock position voice dictation"
LEGACY_VOICE_DESCRIPTION = "Ctrl Swap voice dictation"
VOICE_BINDINGS = (
    "F24",
    "Caps_Lock",
    "Multi_key",
    "code:66",
    "code:58",
    "CONTROL_L + CONTROL_L",
)


def run(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True)
    return result.stdout.strip()


def current_options() -> str:
    try:
        data = json.loads(run("hyprctl", "-j", "getoption", "input:kb_options"))
    except json.JSONDecodeError:
        return ""
    value = data.get("str", "")
    return value if isinstance(value, str) else ""


def clear_legacy_xkb_swap() -> None:
    options = [part.strip() for part in current_options().split(",")
               if part.strip() and part.strip() != "ctrl:swapcaps"]
    safe = ",".join(options).replace("\\", "\\\\").replace('"', '\\"')
    lua = f'hl.config({{ input = {{ kb_options = "{safe}" }} }})'
    result = subprocess.run(["hyprctl", "eval", lua], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Could not remove the legacy XKB swap")


PRIVILEGED_HELPER = r'''
import base64
import json
import os
from pathlib import Path
import subprocess
import sys

payload = json.load(sys.stdin)
allowed = {
    "/etc/keyd/hancore-ctrl-swap.conf",
    "/usr/local/bin/keyd",
    "/usr/local/bin/keyd-application-mapper",
    "/usr/local/lib/systemd/system/keyd.service",
}
files = payload.get("files", {})
removals = payload.get("remove", [])
if any(path not in allowed for path in [*files, *removals]):
    raise SystemExit("refusing an unexpected privileged destination")

for path, encoded in files.items():
    destination = Path(path)
    destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.hancore-tmp")
    temporary.write_bytes(base64.b64decode(encoded, validate=True))
    os.chmod(temporary, 0o755 if path.endswith(("/keyd", "-application-mapper")) else 0o644)
    os.replace(temporary, destination)
for path in removals:
    Path(path).unlink(missing_ok=True)
if "/usr/local/lib/systemd/system/keyd.service" in files:
    subprocess.run(["systemctl", "daemon-reload"], check=True)
if payload.get("enable"):
    subprocess.run(["systemctl", "enable", "keyd"], check=True)
    subprocess.run(["systemctl", "restart", "keyd"], check=True)
elif payload.get("stop"):
    subprocess.run(["systemctl", "stop", "keyd"], check=False)
    subprocess.run(["systemctl", "disable", "keyd"], check=False)
    subprocess.run(["systemctl", "reset-failed", "keyd"], check=False)
elif payload.get("restart"):
    subprocess.run(["systemctl", "restart", "keyd"], check=True)
'''


def root_command(files: dict[str, bytes] | None = None, remove: tuple[str, ...] = (), *, enable: bool = False, restart: bool = False, stop: bool = False) -> None:
    if shutil.which("pkexec") is None:
        raise RuntimeError("pkexec is required to install the keyboard remap")
    encoded = {
        path: base64.b64encode(content).decode("ascii")
        for path, content in (files or {}).items()
    }
    payload = json.dumps({"files": encoded, "remove": list(remove), "enable": enable, "restart": restart, "stop": stop})
    result = subprocess.run(
        ["pkexec", "python3", "-c", PRIVILEGED_HELPER],
        input=payload,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or "Authentication was cancelled or denied")


def keyd_config(swap: bool = False, voice: bool = False) -> str:
    # Four complete states. keyd stays running; only this file changes.
    # Voice off must not leave capslock = f24 in place.
    if swap and voice:
        mapping = "capslock = overload(control, f24)\nleftcontrol = capslock\n"
    elif swap:
        mapping = "capslock = layer(control)\nleftcontrol = capslock\n"
    elif voice:
        mapping = "capslock = f24\n"
    else:
        mapping = "capslock = capslock\n"
    return (
        "# Generated by Omarchy Keyboard Indicator. Do not edit manually.\n"
        f"# schema: {CONFIG_SCHEMA}\n"
        "[ids]\n"
        "*\n"
        "\n"
        "[main]\n"
        f"{mapping}"
    )


def _normalize_keyd(value: str) -> str:
    return "\n".join(
        line for line in value.splitlines() if not line.lstrip().startswith("#")
    )


def keyd_config_matches(swap: bool, voice: bool) -> bool:
    try:
        current = KEYD_DEST.read_text()
    except OSError:
        return False
    # A config without the schema marker was written by a different
    # generation of this plugin; treat it as drift and rebuild.
    return CONFIG_SCHEMA in current and (
        _normalize_keyd(current) == _normalize_keyd(keyd_config(swap, voice))
    )


def ensure_keyd_installed(config_path: pathlib.Path) -> bool:
    if shutil.which("keyd") is not None:
        return False
    if shutil.which("git") is None or shutil.which("make") is None:
        raise RuntimeError("keyd is not installed and git/make are unavailable")
    with tempfile.TemporaryDirectory(prefix="hancore-keyd-") as temp_dir:
        checkout_dir = pathlib.Path(temp_dir) / "keyd"
        clone = subprocess.run(
            ["git", "clone", "--no-checkout", "--depth", "1", KEYD_REPOSITORY, str(checkout_dir)],
            capture_output=True,
            text=True,
        )
        if clone.returncode != 0:
            raise RuntimeError(clone.stderr.strip() or "Could not download keyd")
        fetch = subprocess.run(
            ["git", "-C", str(checkout_dir), "fetch", "--depth", "1", KEYD_REPOSITORY, KEYD_COMMIT],
            capture_output=True,
            text=True,
        )
        if fetch.returncode != 0:
            raise RuntimeError(fetch.stderr.strip() or "Could not fetch the pinned keyd revision")
        checkout = subprocess.run(
            ["git", "-C", str(checkout_dir), "checkout", "--force", "--detach", KEYD_COMMIT],
            capture_output=True,
            text=True,
        )
        if checkout.returncode != 0:
            raise RuntimeError(checkout.stderr.strip() or "Could not select the pinned keyd revision")
        status = subprocess.run(
            ["git", "-C", str(checkout_dir), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True,
            text=True,
        )
        if status.returncode != 0 or status.stdout.strip():
            raise RuntimeError("keyd checkout contains unexpected local changes")
        build = subprocess.run(["make", "-C", str(checkout_dir), "all"], capture_output=True, text=True)
        if build.returncode != 0:
            raise RuntimeError(build.stderr.strip() or "Could not build keyd")
        files = {
            "/usr/local/bin/keyd": (checkout_dir / "bin/keyd").read_bytes(),
            "/usr/local/bin/keyd-application-mapper": (checkout_dir / "bin/keyd-application-mapper").read_bytes(),
            "/usr/local/lib/systemd/system/keyd.service": (
                "[Unit]\nDescription=key remapping daemon\n\n"
                "[Service]\nType=simple\nExecStart=/usr/local/bin/keyd\n\n"
                "[Install]\nWantedBy=multi-user.target\n"
            ).encode(),
            str(KEYD_DEST): config_path.read_bytes(),
        }
    root_command(files, enable=True)
    return True


def _systemctl_quiet(action: str, unit: str = "keyd") -> bool:
    return subprocess.run(
        ["systemctl", action, "--quiet", unit],
        capture_output=True,
        check=False,
    ).returncode == 0


def _keyd_is_active() -> bool:
    return _systemctl_quiet("is-active")


def _keyd_unit_busy() -> bool:
    return _keyd_is_active() or _systemctl_quiet("is-failed")


def remap_is_live(swap: bool, voice: bool) -> bool:
    return keyd_config_matches(swap, voice) and _keyd_is_active()


def _lock_path() -> pathlib.Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / "keyd.lock"


def _apply_keyd_unlocked(swap: bool, voice: bool, *, force: bool = False) -> None:
    config_path = STATE_DIR / "keyd.conf"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not force and remap_is_live(swap, voice):
        return
    config_path.write_text(keyd_config(swap, voice))
    freshly_installed = ensure_keyd_installed(config_path)
    if not freshly_installed:
        root_command({str(KEYD_DEST): config_path.read_bytes()}, enable=True)
    if not remap_is_live(swap, voice):
        raise RuntimeError("keyd is not running the requested remap")


def _sync_unlocked(swap: bool, voice: bool, *, force: bool) -> None:
    # Single choke point for all four state transitions. Preconditions run
    # first, the machine changes second, and the state files are written
    # last: a failure anywhere above leaves the ledger untouched so
    # status()/ensure() can see and repair the drift.
    if voice and shutil.which("voxtype") is None:
        raise RuntimeError("Voxtype is not installed")
    if voice:
        # Bind before keyd: while the previous mapping is still live the
        # bind is inert, so a failed keyd step cannot leave a dead CapsLock.
        install_voice_binds()
    _apply_keyd_unlocked(swap, voice, force=force)
    if voice:
        VOICE_STATE_FILE.write_text("1\n")
    else:
        # keyd has stopped emitting F24 by now; retire the binding.
        remove_owned_voice_bindings()
        VOICE_STATE_FILE.unlink(missing_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if swap:
        STATE_FILE.write_text("1\n")
    else:
        STATE_FILE.unlink(missing_ok=True)


def sync(swap: bool, voice: bool, *, force: bool = False) -> None:
    with _lock_path().open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _sync_unlocked(swap, voice, force=force)


def enable() -> None:
    clear_legacy_xkb_swap()
    sync(True, VOICE_STATE_FILE.exists(), force=True)


def disable() -> None:
    sync(False, VOICE_STATE_FILE.exists(), force=True)


def _owned_voice_binds() -> list[dict]:
    raw = run("hyprctl", "-j", "binds")
    try:
        binds = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [
        item for item in binds
        if item.get("description") in (VOICE_DESCRIPTION, LEGACY_VOICE_DESCRIPTION)
    ]


def remove_owned_voice_bindings() -> None:
    owned = _owned_voice_binds()
    if not owned:
        return
    # Unbind what we actually own plus the legacy key list; skip nameless
    # entries Hyprland cannot be asked to unbind by token.
    keys = {item.get("key") for item in owned}
    keys.update(VOICE_BINDINGS)
    keys.discard("")
    tokens = sorted(keys)
    eval_lua("; ".join(f'hl.unbind("{key}")' for key in tokens))


def eval_lua(lua: str) -> None:
    last_detail = "Hyprland rejected the runtime binding"
    for attempt in range(5):
        result = subprocess.run(
            ["hyprctl", "eval", lua], capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            return
        last_detail = (result.stderr or result.stdout).strip() or last_detail
        if attempt < 4:
            time.sleep(0.25)
    raise RuntimeError(last_detail)


def _voice_bind(key: str, *, release: bool) -> str:
    flags = "release = true, " if release else ""
    return (
        f'hl.bind("{key}", hl.dsp.exec_cmd("voxtype record toggle"), '
        f'{{ {flags}non_consuming = false, '
        f'description = "CapsLock position voice dictation" }})'
    )


def install_voice_binds() -> None:
    # Voice always arrives as F24 from keyd. Do not bind Caps_Lock/Multi_key:
    # those are the physical key only when voice is off.
    owned = _owned_voice_binds()
    if len(owned) == 1 and owned[0].get("key") == "F24" and owned[0].get("release") is True:
        return
    remove_owned_voice_bindings()
    eval_lua(_voice_bind("F24", release=True))


def voice_enable() -> None:
    sync(STATE_FILE.exists(), True, force=True)


def voice_disable() -> None:
    sync(STATE_FILE.exists(), False, force=True)


def ensure() -> None:
    sync(STATE_FILE.exists(), VOICE_STATE_FILE.exists(), force=False)


def status() -> None:
    swap = STATE_FILE.exists()
    voice = VOICE_STATE_FILE.exists()
    print(json.dumps({
        "enabled": swap and KEYD_DEST.exists(),
        "backend": "keyd",
        "keydInstalled": shutil.which("keyd") is not None,
        "voiceEnabled": voice,
        "remapApplied": remap_is_live(swap, voice),
    }))


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    actions = {
        "status": status,
        "enable": enable,
        "disable": disable,
        "ensure": ensure,
        "voice-enable": voice_enable,
        "voice-disable": voice_disable,
    }
    action = actions.get(command)
    if action is None:
        print(f"unknown command: {command}", file=sys.stderr)
        return 2
    try:
        action()
        if command != "status":
            status()
    except Exception as error:
        print(json.dumps({"error": str(error)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
