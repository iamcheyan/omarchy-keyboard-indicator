import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
    id: root
    moduleName: "hancore.ctrl-swap"

    property string swapTool: Qt.resolvedUrl("../scripts/ctrl_swap.py").toString().replace("file://", "")
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

    // Re-apply the swap after shell/Hyprland restarts when the user left it on.
    Component.onCompleted: ensureProcess.running = true

    Process {
        id: ensureProcess
        command: ["python3", root.swapTool, "ensure"]
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
        text: "󰌌"
        tooltipText: "Ctrl Swap — 交换 CapsLock 与 Left Ctrl"
        onPressed: function(buttonCode) {
            if (buttonCode === Qt.LeftButton) root.toggle();
        }
    }
}
