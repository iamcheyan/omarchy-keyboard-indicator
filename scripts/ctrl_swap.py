#!/usr/bin/env python3
"""CapsLock/Left Ctrl remapping and independent per-key Voxtype controls using keyd."""

from __future__ import annotations

import base64
import fcntl
import json
import os
import pathlib
import re
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
KEYD_CONFIG_DIR = pathlib.Path("/etc/keyd")
KEYD_SELECTION_FILE = STATE_DIR / "keyboard_config"
KEYD_REPOSITORY = "https://github.com/rvaiya/keyd.git"
# Pin the source compiled without privileges. The commit hash is the integrity
# check; pkexec receives only the resulting artifact bytes for installation.
KEYD_COMMIT = "f564288ac2b19d2305a5b39023c474805ff8fce5"
CONFIG_SCHEMA = "hancore keyboard-center voice-keys/1"
DEVICE_BLOCK_START = "# BEGIN hancore.keyboard-center managed mappings"
DEVICE_BLOCK_END = "# END hancore.keyboard-center managed mappings"
VOICE_STATE_FILE = STATE_DIR / "voice_enabled"
VOICE_STATE_FILES = {
    "capslock": VOICE_STATE_FILE,
    "leftcontrol": STATE_DIR / "voice_leftcontrol_enabled",
    "rightcontrol": STATE_DIR / "voice_rightcontrol_enabled",
}
VOICE_DESCRIPTION = "Keyboard key voice dictation"
LEGACY_VOICE_DESCRIPTION = "Ctrl Swap voice dictation"
VOICE_BINDINGS = (
    # Legacy physical-key bindings and the previous F24 trigger only.
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
def allowed_path(path):
    return path in allowed or (path.startswith("/etc/keyd/") and path.endswith(".conf"))
if any(not allowed_path(path) for path in [*files, *removals]):
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
    if shutil.which("sudo") is not None and subprocess.run(["sudo", "-n", "true"], check=False).returncode == 0:
        launcher = ["sudo", "-n"]
    elif shutil.which("pkexec") is not None:
        launcher = ["pkexec"]
    else:
        raise RuntimeError("pkexec or passwordless sudo is required to install the keyboard remap")
    encoded = {
        path: base64.b64encode(content).decode("ascii")
        for path, content in (files or {}).items()
    }
    payload = json.dumps({"files": encoded, "remove": list(remove), "enable": enable, "restart": restart, "stop": stop})
    result = subprocess.run(
        [*launcher, "python3", "-c", PRIVILEGED_HELPER],
        input=payload,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or "Authentication was cancelled or denied")


def _voice_keys(voice: bool | set[str] | frozenset[str], voice_keys: set[str] | None = None) -> set[str]:
    if voice_keys is not None:
        selected = set(voice_keys)
    elif isinstance(voice, bool):
        # Preserve the old API: voice=True meant CapsLock dictation.
        selected = {"capslock"} if voice else set()
    else:
        selected = set(voice)
    unknown = selected - VOICE_STATE_FILES.keys()
    if unknown:
        raise ValueError(f"unsupported voice key: {', '.join(sorted(unknown))}")
    return selected


def voice_state_keys() -> set[str]:
    return {key for key, path in VOICE_STATE_FILES.items() if path.exists()}


def keyd_configs() -> list[dict[str, object]]:
    """Return the installed keyd profiles so the UI can identify devices."""
    result = []
    try:
        paths = sorted(KEYD_CONFIG_DIR.glob("*.conf"))
    except OSError:
        paths = []
    for path in paths:
        ids: list[str] = []
        in_ids = False
        try:
            for raw in path.read_text().splitlines():
                line = raw.strip()
                if line.startswith("["):
                    in_ids = line.lower() == "[ids]"
                    continue
                if in_ids and line and not line.startswith("#"):
                    ids.append(line)
        except OSError:
            continue
        result.append({"path": str(path), "name": path.name, "ids": ids,
                       "label": f"{path.name} · {', '.join(ids) or 'unknown device'}"})
    return result


def selected_keyd_config() -> str:
    try:
        value = KEYD_SELECTION_FILE.read_text().strip()
    except OSError:
        value = ""
    available = {item["path"] for item in keyd_configs()}
    return value if value in available else str(KEYD_DEST)


def select_keyd_config(path: str) -> None:
    available = {item["path"] for item in keyd_configs()}
    if path not in available:
        raise RuntimeError(f"Unknown keyd configuration: {path}")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    KEYD_SELECTION_FILE.write_text(path + "\n")
    # A profile change is meaningful immediately when a remap is active.
    sync(STATE_FILE.exists(), voice_state_keys(), force=True)


def keyd_config(swap: bool = False, voice: bool | set[str] = False, *, voice_keys: set[str] | None = None) -> str | None:
    # Match the original behavior: Ctrl keys use overload so Ctrl chords stay
    # intact; a standalone Ctrl emits F24 after release and toggles Voxtype.
    selected = _voice_keys(voice, voice_keys)
    mapping = {
        "capslock": "layer(control)" if swap else "capslock",
        "leftcontrol": "capslock" if swap else None,
    }
    if "capslock" in selected:
        mapping["capslock"] = "overload(control, f24)" if swap else "f24"
    if "leftcontrol" in selected:
        mapping["leftcontrol"] = "overload(control, f24)"
    if "rightcontrol" in selected:
        mapping["rightcontrol"] = "overload(control, f24)"
    if not swap and not selected:
        # keyd applies exactly one config per device. Leaving our wildcard
        # config installed in the neutral state could override the user's
        # own /etc/keyd/default.conf and discard unrelated mappings.
        return None
    body = "\n".join(
        f"{key} = {value}" for key, value in mapping.items() if value is not None
    ) + "\n"
    return (
        "# Generated by Omarchy Keyboard Indicator. Do not edit manually.\n"
        f"# schema: {CONFIG_SCHEMA}\n"
        "[ids]\n"
        "*\n"
        "\n"
        "[main]\n"
        f"{body}"
    )


def _normalize_keyd(value: str) -> str:
    return "\n".join(
        line for line in value.splitlines() if not line.lstrip().startswith("#")
    )


def keyd_config_matches(swap: bool, voice: bool | set[str], *, voice_keys: set[str] | None = None) -> bool:
    expected = keyd_config(swap, voice, voice_keys=voice_keys)
    destination = pathlib.Path(selected_keyd_config())
    if expected is None:
        # Neutral means this plugin owns no keyd configuration.
        if destination == KEYD_DEST:
            return not KEYD_DEST.exists()
        try:
            return DEVICE_BLOCK_START not in destination.read_text()
        except OSError:
            return True
    try:
        current = destination.read_text()
    except OSError:
        return False
    # A config without the schema marker was written by a different
    # generation of this plugin; treat it as drift and rebuild.
    if destination == KEYD_DEST:
        return CONFIG_SCHEMA in current and _normalize_keyd(current) == _normalize_keyd(expected)
    block = _device_block(expected)
    return _normalize_keyd(block) in _normalize_keyd(current)


def _device_block(config: str) -> str:
    body = config.split("[main]\n", 1)[-1]
    return f"{DEVICE_BLOCK_START}\n[main]\n{body}{DEVICE_BLOCK_END}\n"


def _without_device_block(content: str) -> str:
    pattern = re.escape(DEVICE_BLOCK_START) + r"\n.*?" + re.escape(DEVICE_BLOCK_END) + r"\n?"
    return re.sub(pattern, "", content, flags=re.DOTALL)


def pinned_keyd_commit() -> str:
    if re.fullmatch(r"[0-9a-fA-F]{40}", KEYD_COMMIT) is None:
        raise RuntimeError("KEYD_COMMIT must be a full 40-character commit SHA")
    return KEYD_COMMIT.lower()


def ensure_keyd_installed(config_path: pathlib.Path) -> bool:
    if shutil.which("keyd") is not None:
        return False
    if shutil.which("git") is None or shutil.which("make") is None:
        raise RuntimeError("keyd is not installed and git/make are unavailable")
    commit = pinned_keyd_commit()
    with tempfile.TemporaryDirectory(prefix="hancore-keyd-") as temp_dir:
        checkout_dir = pathlib.Path(temp_dir) / "keyd"
        initialize = subprocess.run(
            ["git", "init", str(checkout_dir)],
            capture_output=True,
            text=True,
        )
        if initialize.returncode != 0:
            raise RuntimeError(initialize.stderr.strip() or "Could not initialize the keyd checkout")
        fetch = subprocess.run(
            ["git", "-C", str(checkout_dir), "fetch", "--depth", "1", KEYD_REPOSITORY, commit],
            capture_output=True,
            text=True,
        )
        if fetch.returncode != 0:
            raise RuntimeError(fetch.stderr.strip() or "Could not fetch the pinned keyd revision")
        checkout = subprocess.run(
            ["git", "-C", str(checkout_dir), "checkout", "--force", "--detach", commit],
            capture_output=True,
            text=True,
        )
        if checkout.returncode != 0:
            raise RuntimeError(checkout.stderr.strip() or "Could not select the pinned keyd revision")
        resolved = subprocess.run(
            ["git", "-C", str(checkout_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        if resolved.returncode != 0 or resolved.stdout.strip().lower() != commit:
            raise RuntimeError("The fetched keyd revision does not match KEYD_COMMIT")
        status = subprocess.run(
            ["git", "-C", str(checkout_dir), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True,
            text=True,
        )
        if status.returncode != 0 or status.stdout.strip():
            raise RuntimeError("keyd checkout contains unexpected local changes")
        build = subprocess.run(["make", "all"], cwd=checkout_dir, capture_output=True, text=True)
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


def remap_is_live(swap: bool, voice: bool | set[str]) -> bool:
    if keyd_config(swap, voice) is None:
        # keyd may still be serving the user's own configurations.
        return keyd_config_matches(swap, voice)
    return keyd_config_matches(swap, voice) and _keyd_is_active()


def _lock_path() -> pathlib.Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / "keyd.lock"


def _apply_keyd_unlocked(swap: bool, voice: bool | set[str], *, force: bool = False) -> None:
    config_path = STATE_DIR / "keyd.conf"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not force and remap_is_live(swap, voice):
        return
    config = keyd_config(swap, voice)
    destination = pathlib.Path(selected_keyd_config())
    if config is None:
        # Remove our wildcard config instead of installing an identity map.
        # Restart keyd so any user-owned config can become active again.
        config_path.unlink(missing_ok=True)
        if destination == KEYD_DEST:
            if KEYD_DEST.exists():
                root_command(remove=(str(KEYD_DEST),), restart=_keyd_unit_busy())
        elif destination.exists():
            cleaned = _without_device_block(destination.read_text())
            root_command({str(destination): cleaned.encode()}, restart=_keyd_unit_busy())
    else:
        if destination == KEYD_DEST:
            config_path.write_text(config)
            payload = config_path.read_bytes()
        else:
            base = _without_device_block(destination.read_text() if destination.exists() else "")
            payload = (base.rstrip() + "\n\n" + _device_block(config)).encode()
            config_path.write_bytes(payload)
        freshly_installed = ensure_keyd_installed(config_path)
        if not freshly_installed:
            root_command(
                {str(destination): payload},
                remove=(str(KEYD_DEST),) if destination != KEYD_DEST and KEYD_DEST.exists() else (),
                enable=True,
            )
    if not remap_is_live(swap, voice):
        raise RuntimeError("keyd is not running the requested remap")


def _sync_unlocked(swap: bool, voice: bool | set[str], *, force: bool) -> None:
    # Single choke point for all four state transitions. Preconditions run
    # first, the machine changes second, and the state files are written
    # last: a failure anywhere above leaves the ledger untouched so
    # status()/ensure() can see and repair the drift.
    selected = _voice_keys(voice)
    if selected and shutil.which("voxtype") is None:
        raise RuntimeError("Voxtype is not installed")
    if selected:
        install_voice_binds()
    _apply_keyd_unlocked(swap, voice, force=force)
    for key, path in VOICE_STATE_FILES.items():
        if key in selected:
            path.write_text("1\n")
        else:
            path.unlink(missing_ok=True)
    if not selected:
        # keyd has stopped emitting F24 by now; retire the binding.
        remove_owned_voice_bindings()
        VOICE_STATE_FILE.unlink(missing_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if swap:
        STATE_FILE.write_text("1\n")
    else:
        STATE_FILE.unlink(missing_ok=True)


def sync(swap: bool, voice: bool | set[str], *, force: bool = False) -> None:
    with _lock_path().open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _sync_unlocked(swap, voice, force=force)


def enable() -> None:
    clear_legacy_xkb_swap()
    sync(True, voice_state_keys(), force=True)


def disable() -> None:
    sync(False, voice_state_keys(), force=True)


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


def _voice_bind(*, release: bool) -> str:
    flags = "release = true, " if release else ""
    return (
        f'hl.bind("F24", hl.dsp.exec_cmd("voxtype record toggle"), '
        f'{{ {flags}non_consuming = false, '
        f'description = "{VOICE_DESCRIPTION}" }})'
    )


def install_voice_binds() -> None:
    # F24 is the plugin-owned synthetic trigger. F9 remains the user's normal
    # Voxtype toggle and is never modified by this plugin.
    owned = _owned_voice_binds()
    if len(owned) == 1 and owned[0].get("key") == "F24" and owned[0].get("release") is True:
        return
    remove_owned_voice_bindings()
    eval_lua(_voice_bind(release=True))


def voice_enable(key: str = "capslock") -> None:
    selected = voice_state_keys()
    selected.add(_voice_keys(False, {key}).pop())
    sync(STATE_FILE.exists(), selected, force=True)


def voice_disable(key: str = "capslock") -> None:
    selected = voice_state_keys()
    selected.discard(_voice_keys(False, {key}).pop())
    sync(STATE_FILE.exists(), selected, force=True)


def ensure() -> None:
    sync(STATE_FILE.exists(), voice_state_keys(), force=False)


def status() -> None:
    swap = STATE_FILE.exists()
    voice_keys = voice_state_keys()
    print(json.dumps({
        "enabled": swap and pathlib.Path(selected_keyd_config()).exists(),
        "backend": "keyd",
        "keydInstalled": shutil.which("keyd") is not None,
        "voiceEnabled": bool(voice_keys),
        "voiceCapslockEnabled": "capslock" in voice_keys,
        "voiceLeftControlEnabled": "leftcontrol" in voice_keys,
        "voiceRightControlEnabled": "rightcontrol" in voice_keys,
        "voiceKeys": sorted(voice_keys),
        "keydConfigs": keyd_configs(),
        "selectedKeydConfig": selected_keyd_config(),
        "remapApplied": remap_is_live(swap, voice_keys),
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
        "select-keyd-config": select_keyd_config,
    }
    action = actions.get(command)
    if action is None:
        print(f"unknown command: {command}", file=sys.stderr)
        return 2
    try:
        if command == "select-keyd-config":
            if len(sys.argv) != 3:
                raise RuntimeError("usage: ctrl_swap.py select-keyd-config <path>")
            action(sys.argv[2])
        elif command in {"voice-enable", "voice-disable"}:
            action(sys.argv[2] if len(sys.argv) > 2 else "capslock")
        else:
            action()
        if command != "status":
            status()
    except Exception as error:
        print(json.dumps({"error": str(error)}))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
