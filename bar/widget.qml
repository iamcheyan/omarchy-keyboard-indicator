import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
    id: root
    moduleName: "hancore.keyboard-center"

    property string swapTool: Qt.resolvedUrl("../scripts/ctrl_swap.py").toString().replace("file://", "")
    property string inputTool: Qt.resolvedUrl("../scripts/keyboard_center.py").toString().replace("file://", "")
    property string inputBadge: "󰌌"
    property string inputTooltip: "Keyboard Indicator"
    readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false

    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    function injectPanel() {
        if (!panelLoader.item) return;
        panelLoader.item.bar = root.bar;
        panelLoader.item.anchorItem = button;
        panelLoader.item.hostWidget = root;
    }

    function open() {
        if (panelLoader.item) {
            panelLoader.item.open();
            return;
        }
        panelLoader.active = true;
        Qt.callLater(function() {
            if (panelLoader.item) panelLoader.item.open();
        });
    }

    function close() {
        if (panelLoader.item) panelLoader.item.close();
    }

    function toggle() {
        if (root.opened) root.close();
        else root.open();
    }

    onBarChanged: injectPanel()

    function applyInputStatus(raw) {
        try {
            const data = JSON.parse(raw);
            if (data.error) return;
            const schema = data.schema || "";
            const choices = Array.isArray(data.schemas) ? data.schemas : [];
            const selected = choices.find(item => item.id === schema);
            root.inputBadge = selected?.badge || (data.inputMethod === "keyboard-jp" ? "JP" : (data.inputMethod === "keyboard-us" ? "A" : (data.inputMethod ? "中" : "󰌌")));
            root.inputTooltip = (data.displayName || "Input Method") + (data.variant ? " · " + data.variant : "");
        } catch (error) { }
    }

    Timer { id: inputPoll; interval: 1500; repeat: true; running: true; onTriggered: inputStatus.running = true }
    Process {
        id: inputStatus
        command: ["python3", root.inputTool, "status"]
        running: true
        property string buffer: ""
        stdout: SplitParser { splitMarker: "\n"; onRead: function(line) { inputStatus.buffer += line; } }
        onRunningChanged: {
            if (!running) {
                root.applyInputStatus(buffer);
                buffer = "";
            }
        }
    }

    // Re-apply the user-level voice binding after the shell has finished
    // registering Hyprland runtime bindings. keyd itself is persistent.
    Component.onCompleted: ensureDelay.start()

    Timer {
        id: ensureDelay
        interval: 1200
        repeat: false
        onTriggered: {
            ensureProcess.running = true;
            layoutEnsureProcess.running = true;
        }
    }

    Process {
        id: ensureProcess
        command: ["python3", root.swapTool, "ensure"]
        running: false
    }

    Process {
        id: layoutEnsureProcess
        command: ["python3", root.inputTool, "ensure-layout"]
        running: false
    }

    Loader {
        id: panelLoader
        active: false
        source: Qt.resolvedUrl("../CtrlSwapPanel.qml")
        visible: false
        onLoaded: { root.injectPanel(); Qt.callLater(root.injectPanel); }
    }

    BarIconButton {
        id: button
        bar: root.bar
        text: root.inputBadge
        tooltipText: root.inputTooltip
        onPressed: function(buttonCode) {
            if (buttonCode === Qt.LeftButton) root.toggle();
        }
    }
}
