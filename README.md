# Ctrl Swap

Ctrl Swap 是一个 Omarchy 体验增强插件：在顶栏提供一个开关，把 **CapsLock 与 Left Ctrl 在 XKB 层交换**。适合习惯把 Ctrl 放在小拇指 home 位（HHKB / 老程序员布局）的人。

## 特性

- 单一开关：开启即交换，关闭即还原，没有多余选项。
- **XKB 层生效**：对所有应用同时成立——GUI、终端、tmux 内层、甚至 SSH 到远程机器的会话里，物理 CapsLock 发出的都是真正的 `Control_L`。
- **非侵入**：通过 Lua 桥（`hyprctl eval 'hl.config(...)'`）运行时应用，不写入 `~/.config/hypr/` 的任何文件；关闭开关立即还原原按键映射。
- **重启记忆**：开关状态持久化；Hyprland/shell 重启后插件自动重新应用。
- 无守护进程、无第二个 Quickshell 实例、不需要 root。

## 安装

```sh
omarchy plugin add https://github.com/iamcheyan/omarchy-ctrl-swap.git --enable
```

顶栏出现键盘图标，点开面板，打开「交换 CapsLock ⇄ Ctrl」即可。

## 已知边界

- Compose 键冲突：若你的 `kb_options` 含有 `compose:caps`（Omarchy 默认），交换期间 Compose 功能会跟随 CapsLock 键名落到物理左 Ctrl 上。不用 Compose 可无视；需要保留请自行把 compose 挪到其他键位。
- Hyprland 重载/重启会把 `kb_options` 重置为配置文件的值。本插件的 service 会在 shell 启动时按持久化的开关状态自动重新应用；手动执行 `omarchy reload` 后重开一次开关即可。
- 只交换 Left Ctrl；Right Ctrl 不受影响。

## 工作原理

```text
hyprctl eval 'hl.config({ input = { kb_options = "<原选项>,ctrl:swapcaps" } })'   # 开启
hyprctl eval 'hl.config({ input = { kb_options = "<原选项>" } })'                 # 关闭
```

脚本只做字符串级的选项增删：先读取当前生效值，追加或移除 `ctrl:swapcaps` 后写回。开关状态存于 `~/.local/state/hancore.ctrl-swap/enabled`。

## 验证

```sh
omarchy plugin validate .
qmllint -I /usr/share/omarchy/shell bar/widget.qml CtrlSwapPanel.qml
python3 -m py_compile scripts/ctrl_swap.py
```

## License

MIT. See [LICENSE](LICENSE).
