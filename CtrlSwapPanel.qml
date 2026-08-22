import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
    id: root
    moduleName: "hancore.ctrl-swap"
    manageIpc: false

    property var anchorItem: null
    property var hostWidget: null
    property string swapTool: Qt.resolvedUrl("../scripts/ctrl_swap.py").toString().replace("file://", "")
    property bool loading: false
    property bool enabled_: false
    property string optionsText: ""
    property string statusText: ""

    function open() { root.controller.show(); refresh(); }
    function close() { root.controller.hide(); }
    function toggle() { root.opened ? root.close() : root.open(); }
    function refresh() {
        if (!readProcess.running) readProcess.running = true;
    }

    function applySnapshot(raw) {
        try {
            const data = JSON.parse(raw);
            if (data.error) {
                root.statusText = data.error;
                return;
            }
            root.enabled_ = data.enabled === true;
            root.optionsText = data.options || "";
        } catch (error) {
            root.statusText = "无法读取当前键盘选项";
        }
    }

    function setSwap(on) {
        if (writeProcess.running) return;
        writeProcess.command = ["python3", root.swapTool, on ? "enable" : "disable"];
        root.loading = true;
        root.statusText = on ? "正在交换 CapsLock 和 Left Ctrl…" : "正在恢复原按键…";
        writeProcess.running = true;
    }

    Process {
        id: readProcess
        command: ["python3", root.swapTool, "status"]
        running: false
        property string buffer: ""
        stdout: SplitParser { splitMarker: "\n"; onRead: function(line) { readProcess.buffer += line; } }
        onRunningChanged: {
            if (!running) {
                root.applySnapshot(readProcess.buffer);
                readProcess.buffer = "";
                root.loading = false;
            }
        }
    }

    Process {
        id: writeProcess
        command: ["python3", root.swapTool, "status"]
        running: false
        property string buffer: ""
        stdout: SplitParser { splitMarker: "\n"; onRead: function(line) { writeProcess.buffer += line; } }
        onRunningChanged: {
            if (!running) {
                root.loading = false;
                root.applySnapshot(writeProcess.buffer);
                writeProcess.buffer = "";
                root.statusText = root.enabled_ ? "已交换：物理 CapsLock 现在是 Left Ctrl"
                                                : "已恢复原始按键映射";
                clearStatus.restart();
            }
        }
    }

    Timer { id: clearStatus; interval: 4000; repeat: false; onTriggered: root.statusText = "" }

    KeyboardPanel {
        id: panel
        anchorItem: root.anchorItem
        owner: root.hostWidget || root
        bar: root.bar
        open: root.opened
        focusTarget: keyCatcher
        contentWidth: panel.fittedContentWidth(Style.space(300))
        contentHeight: panel.fittedContentHeight(content.implicitHeight)

        PanelKeyCatcher {
            id: keyCatcher
            anchors.fill: parent
            onCloseRequested: root.close()

            Column {
                id: content
                width: parent.width
                spacing: Style.space(10)

                Item {
                    width: parent.width
                    height: titleText.implicitHeight

                    Text {
                        id: titleText
                        anchors.left: parent.left
                        text: "Ctrl Swap"
                        color: root.barForeground
                        font.pixelSize: Style.font.bodyLarge
                    }

                    Text {
                        anchors.right: parent.right
                        text: root.enabled_ ? "已交换" : "未启用"
                        color: root.enabled_ ? Color.accent : Color.foregroundDim
                        font.pixelSize: Style.font.bodySmall
                    }
                }

                Text {
                    width: parent.width
                    text: "在 XKB 层交换 CapsLock 与 Left Ctrl。运行时生效，不写入任何配置文件；关闭即还原。"
                    color: Color.foregroundDim
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                }

                Rectangle {
                    width: parent.width
                    height: switchRow.implicitHeight + Style.space(16)
                    radius: Style.radius(8)
                    color: root.enabled_
                        ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.22)
                        : Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.07)

                    RowLayout {
                        id: switchRow
                        anchors.fill: parent
                        anchors.margins: Style.space(8)

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0

                            Text {
                                text: "交换 CapsLock ⇄ Ctrl"
                                color: root.barForeground
                                font.pixelSize: Style.font.bodyMedium
                            }
                            Text {
                                Layout.fillWidth: true
                                text: "对所有应用与 tmux 内层同时生效"
                                color: Color.foregroundDim
                                font.pixelSize: Style.font.bodySmall
                                elide: Text.ElideRight
                            }
                        }

                        Switch {
                            checked: root.enabled_
                            enabled: !root.loading
                            onToggled: root.setSwap(checked)
                        }
                    }
                }

                Text {
                    width: parent.width
                    text: root.loading ? "处理中…" : (root.statusText !== "" ? root.statusText : ("当前 kb_options: " + (root.optionsText === "" ? "(空)" : root.optionsText)))
                    color: Color.foregroundDim
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
