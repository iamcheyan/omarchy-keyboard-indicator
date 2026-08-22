#!/usr/bin/env python3
"""Fcitx5 input-method and Hyprland keyboard-layout bridge for Keyboard Indicator."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

FCITX = "org.fcitx.Fcitx5"
RIME_PATH = "/rime"
RIME_IFACE = "org.fcitx.Fcitx.Rime1"
LAYOUT_STATE = pathlib.Path(os.environ.get("XDG_STATE_HOME", pathlib.Path.home() / ".local/state")) / "hancore.keyboard-center/layouts.json"
DEFAULT_LAYOUTS = ["us", "jp", "gb", "de", "fr", "ru", "cn"]

DEFAULT_SCHEMAS = [
    {"id": "sbzr", "language": "zh", "name": "Chinese", "variant": "Natural input", "badge": "中"},
    {"id": "sbzr_mix", "language": "zh", "name": "Chinese", "variant": "Mixed input", "badge": "混"},
    {"id": "easy_en", "language": "en", "name": "English", "variant": "Easy English", "badge": "A"},
    {"id": "jaroomaji", "language": "ja", "name": "Japanese", "variant": "Romaji", "badge": "あ"},
]


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def schema_file() -> pathlib.Path:
    config_home = os.environ.get("SUMIKA_SHELL_CONFIG_HOME") or os.path.join(
        os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "sumika-shell"
    )
    return pathlib.Path(config_home) / "input-method" / "schemas.json"


def schemas() -> list[dict[str, str]]:
    try:
        data = json.loads(schema_file().read_text(encoding="utf-8"))
        value = data.get("schemas", [])
        if isinstance(value, list) and value:
            return value
    except (OSError, json.JSONDecodeError):
        pass
    return DEFAULT_SCHEMAS


def tuple_value(output: str) -> str:
    start = output.find("'")
    end = output.find("'", start + 1) if start >= 0 else -1
    return output[start + 1:end] if start >= 0 and end > start else ""


def rime_call(method: str, *args: str) -> subprocess.CompletedProcess[str]:
    return run(["gdbus", "call", "--session", "--dest", FCITX,
                "--object-path", RIME_PATH, "--method", f"{RIME_IFACE}.{method}", *args])


def input_status() -> dict[str, object]:
    current = run(["fcitx5-remote", "-n"]) if shutil.which("fcitx5-remote") else None
    im = current.stdout.strip() if current and current.returncode == 0 else ""
    schema = ""
    if im == "rime" and shutil.which("gdbus"):
        result = rime_call("GetCurrentSchema")
        if result.returncode == 0:
            schema = tuple_value(result.stdout)
    info = next((item for item in schemas() if item.get("id") == schema), {})
    if im == "rime":
        display = info.get("name", "Rime")
        variant = info.get("variant", schema or "Unknown schema")
    elif im:
        display, variant = im, "Direct input"
    else:
        display, variant = "Unavailable", "Fcitx5 is not running"
    return {"available": bool(im), "inputMethod": im, "schema": schema,
            "displayName": display, "variant": variant, "schemas": schemas()}


def layout_status() -> dict[str, object]:
    if not shutil.which("hyprctl"):
        return {"layouts": [], "currentLayout": "", "layoutNames": {}}
    result = run(["hyprctl", "-j", "devices"])
    try:
        keyboards = json.loads(result.stdout).get("keyboards", [])
    except json.JSONDecodeError:
        keyboards = []
    main = next((item for item in keyboards if item.get("main")), keyboards[0] if keyboards else {})
    configured = [item.strip() for item in str(main.get("layout", "")).split(",") if item.strip()]
    saved = {}
    try:
        saved = json.loads(LAYOUT_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    layouts = saved.get("layouts", []) if isinstance(saved.get("layouts"), list) else []
    if not layouts:
        layouts = configured if len(configured) > 1 else DEFAULT_LAYOUTS
    active = str(main.get("active_keymap", ""))
    index = int(main.get("active_layout_index", 0) or 0)
    current = layouts[index] if index < len(layouts) else ""
    if not current:
        aliases = {"Japanese": "jp", "English (US)": "us", "English (UK)": "gb", "German": "de", "French": "fr", "Russian": "ru", "Chinese": "cn"}
        current = next((code for label, code in aliases.items() if label in active), layouts[0] if layouts else "")
    return {"layouts": layouts, "currentLayout": current,
            "activeKeymap": active,
            "layoutNames": {"us": "English (US)", "us_intl": "English (Intl)", "gb": "English (UK)",
                            "de": "German", "fr": "French", "ru": "Russian", "cn": "Chinese", "jp": "Japanese (JIS)"}}


def status() -> None:
    result = input_status()
    result.update(layout_status())
    print(json.dumps(result, ensure_ascii=False))


def set_schema(schema: str) -> None:
    if schema not in {item.get("id") for item in schemas()}:
        raise RuntimeError(f"Unsupported input method schema: {schema}")
    if run(["fcitx5-remote", "-s", "rime"]).returncode != 0:
        raise RuntimeError("Fcitx5 is not running")
    last_error = "Unable to select input method schema"
    for _ in range(8):
        result = rime_call("SetSchema", schema)
        if result.returncode == 0 and input_status().get("schema") == schema:
            return
        last_error = result.stderr.strip() or last_error
        time.sleep(0.08)
    raise RuntimeError(last_error)


def set_layout(layout: str) -> None:
    state = layout_status()
    layouts = state["layouts"]
    if layout not in layouts:
        raise RuntimeError(f"Keyboard layout is not configured: {layout}")
    layout_list = ",".join(layouts)
    lua = f'hl.config({{ input = {{ kb_layout = "{layout_list}" }} }})'
    result = run(["hyprctl", "eval", lua])
    if result.returncode == 0:
        result = run(["hyprctl", "switchxkblayout", "all", str(layouts.index(layout))])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to switch keyboard layout")
    LAYOUT_STATE.parent.mkdir(parents=True, exist_ok=True)
    LAYOUT_STATE.write_text(json.dumps({"layouts": layouts, "current": layout}, indent=2) + "\n", encoding="utf-8")


def ensure_layout() -> None:
    try:
        saved = json.loads(LAYOUT_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    layouts = saved.get("layouts", [])
    current = saved.get("current", "")
    if not isinstance(layouts, list) or not layouts or current not in layouts:
        return
    layout_list = ",".join(layouts)
    lua = f'hl.config({{ input = {{ kb_layout = "{layout_list}" }} }})'
    result = run(["hyprctl", "eval", lua])
    if result.returncode == 0:
        run(["hyprctl", "switchxkblayout", "all", str(layouts.index(current))])


def main() -> int:
    try:
        action = sys.argv[1] if len(sys.argv) > 1 else "status"
        if action == "status":
            status()
        elif action == "schema" and len(sys.argv) == 3:
            set_schema(sys.argv[2]); status()
        elif action == "layout" and len(sys.argv) == 3:
            set_layout(sys.argv[2]); status()
        elif action == "ensure-layout":
            ensure_layout(); status()
        else:
            raise RuntimeError("usage: keyboard_center.py status|schema <id>|layout <code>")
        return 0
    except Exception as error:
        print(json.dumps({"error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
