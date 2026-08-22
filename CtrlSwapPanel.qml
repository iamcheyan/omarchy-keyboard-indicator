import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
    id: root
    moduleName: "hancore.keyboard-center"
    manageIpc: false

    property var anchorItem: null
    property var hostWidget: null
    property string swapTool: Qt.resolvedUrl("scripts/ctrl_swap.py").toString().replace("file://", "")
    property string inputTool: Qt.resolvedUrl("scripts/keyboard_center.py").toString().replace("file://", "")
    property bool loading: false
    property bool enabled_: false
    property bool voiceEnabled_: false
    property string optionsText: ""
    property string statusText: ""
    property string operation: ""
    property string inputMethodName: "Unavailable"
    property string inputMethodVariant: "Fcitx5 is not running"
    property string inputSchema: ""
    property var inputSchemas: []
    property var inputDropdownOptions: []
    property string inputSelectionValue: ""
    property var keyboardLayouts: []
    property var keyboardLayoutOptions: []
    property string currentKeyboardLayout: ""
    property var keyboardLayoutNames: ({})

    function open() { root.controller.show(); refresh(); }
    function close() { root.controller.hide(); }
    function toggle() { root.opened ? root.close() : root.open(); }
    function refresh() {
        if (!readProcess.running) readProcess.running = true;
        if (!inputReadProcess.running) inputReadProcess.running = true;
    }

    function applySnapshot(raw) {
        try {
            const data = JSON.parse(raw);
            if (data.error) {
                root.statusText = data.error;
                return;
            }
            root.enabled_ = data.enabled === true;
            root.voiceEnabled_ = data.voiceEnabled === true;
            root.optionsText = data.options || "";
        } catch (error) {
            root.statusText = "Could not read the current keyboard options.";
        }
    }

    function applyInputSnapshot(raw) {
        try {
            const data = JSON.parse(raw);
            if (data.error) return;
            root.inputMethodName = data.displayName || "Unavailable";
            root.inputMethodVariant = data.variant || "";
            root.inputSchema = data.schema || "";
            root.inputSchemas = Array.isArray(data.schemas) ? data.schemas : [];
            var inputOptions = [];
            if (root.inputSchema !== "") {
                for (var i = 0; i < root.inputSchemas.length; i++) {
                    var schema = root.inputSchemas[i];
                    inputOptions.push({
                        value: String(schema.id || ""),
                        label: (schema.badge ? schema.badge + "  " : "")
                            + String(schema.name || schema.id || "")
                            + (schema.variant ? " · " + schema.variant : "")
                    });
                }
                root.inputSelectionValue = root.inputSchema;
            } else if (data.inputMethod) {
                inputOptions.push({value: "__direct__", label: root.inputMethodName + " · " + root.inputMethodVariant});
                root.inputSelectionValue = "__direct__";
            } else {
                inputOptions.push({value: "__unavailable__", label: "Fcitx5 unavailable"});
                root.inputSelectionValue = "__unavailable__";
            }
            root.inputDropdownOptions = inputOptions;
            inputMethodDropdown.value = root.inputSelectionValue;
            root.keyboardLayouts = Array.isArray(data.layouts) ? data.layouts : [];
            root.currentKeyboardLayout = data.currentLayout || "";
            root.keyboardLayoutNames = data.layoutNames || ({});
            var layoutOptions = [];
            for (var j = 0; j < root.keyboardLayouts.length; j++) {
                var layout = root.keyboardLayouts[j];
                layoutOptions.push({
                    value: String(layout),
                    label: String(root.keyboardLayoutNames[layout] || layout.toUpperCase())
                });
            }
            root.keyboardLayoutOptions = layoutOptions;
            keyboardLayoutDropdown.value = root.currentKeyboardLayout;
        } catch (error) { }
    }

    function setInputSchema(schema) {
        if (schema === "__direct__" || schema === "__unavailable__") return;
        inputActionProcess.command = ["python3", root.inputTool, "schema", schema];
        inputActionProcess.running = true;
    }

    function setKeyboardLayout(layout) {
        inputActionProcess.command = ["python3", root.inputTool, "layout", layout];
        inputActionProcess.running = true;
    }

    function setSwap(on) {
        if (writeProcess.running) return;
        writeProcess.command = ["python3", root.swapTool, on ? "enable" : "disable"];
        root.loading = true;
        root.operation = "swap";
        root.statusText = on
            ? "Installing the hardware remap… Authentication may be requested."
            : "Removing the hardware remap… Authentication may be requested.";
        writeProcess.running = true;
    }

    function setVoice(on) {
        if (writeProcess.running) return;
        writeProcess.command = ["python3", root.swapTool, on ? "voice-enable" : "voice-disable"];
        root.loading = true;
        root.operation = "voice";
        root.statusText = on ? "Enabling CapsLock-position dictation…" : "Disabling CapsLock-position dictation…";
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
                root.applySnapshot(buffer);
                buffer = "";
                root.loading = false;
            }
        }
    }

    Process {
        id: inputReadProcess
        command: ["python3", root.inputTool, "status"]
        running: false
        property string buffer: ""
        stdout: SplitParser { splitMarker: "\n"; onRead: function(line) { inputReadProcess.buffer += line; } }
        onRunningChanged: {
            if (!running) {
                root.applyInputSnapshot(buffer);
                buffer = "";
            }
        }
    }

    Process {
        id: inputActionProcess
        command: ["python3", root.inputTool, "status"]
        running: false
        property string buffer: ""
        stdout: SplitParser { splitMarker: "\n"; onRead: function(line) { inputActionProcess.buffer += line; } }
        onRunningChanged: {
            if (!running) {
                root.applyInputSnapshot(buffer);
                buffer = "";
                inputReadProcess.running = true;
            }
        }
    }

    Process {
        id: writeProcess
        command: ["python3", root.swapTool, "status"]
        running: false
        property string buffer: ""
        property string errorBuffer: ""
        stdout: SplitParser { splitMarker: "\n"; onRead: function(line) { writeProcess.buffer += line; } }
        stderr: SplitParser { splitMarker: "\n"; onRead: function(line) { writeProcess.errorBuffer += line; } }
        onRunningChanged: {
            if (!running) {
                root.loading = false;
                const output = buffer;
                const errorOutput = errorBuffer;
                root.applySnapshot(buffer);
                buffer = "";
                errorBuffer = "";
                if (errorOutput !== "" || output.indexOf('"error"') !== -1) {
                    if (root.statusText === "") root.statusText = "Could not apply the keyboard mapping.";
                } else {
                    root.statusText = root.operation === "voice"
                        ? (root.voiceEnabled_ ? "The CapsLock-position key now toggles dictation." : "CapsLock dictation is disabled.")
                        : (root.enabled_ ? "Hardware Ctrl swap is active." : "The original key mapping is restored.");
                }
                root.operation = "";
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
        contentWidth: panel.fittedContentWidth(Style.space(480))
        contentHeight: panel.fittedContentHeight(content.implicitHeight)

        PanelKeyCatcher {
            id: keyCatcher
            anchors.fill: parent
            onCloseRequested: root.close()

            Column {
                id: content
                width: parent.width
                spacing: Style.space(12)

                KeyboardDropdown {
                    id: inputMethodDropdown
                    width: parent.width
                    label: "Input Method · " + root.inputMethodName + (root.inputMethodVariant !== "" ? " · " + root.inputMethodVariant : "")
                    value: root.inputSelectionValue
                    options: root.inputDropdownOptions
                    foreground: root.barForeground
                    background: Color.background
                    accent: Color.accent
                    onChanged: function(value) { root.setInputSchema(value); }
                }

                KeyboardDropdown {
                    id: keyboardLayoutDropdown
                    width: parent.width
                    label: "Keyboard Layout"
                    value: root.currentKeyboardLayout
                    options: root.keyboardLayoutOptions
                    foreground: root.barForeground
                    background: Color.background
                    accent: Color.accent
                    onChanged: function(value) { root.setKeyboardLayout(value); }
                }

                Item {
                    width: parent.width
                    height: Style.space(40)

                    Text {
                        width: Style.space(32)
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        text: "󰌌"
                        color: root.barForeground
                        horizontalAlignment: Text.AlignHCenter
                        font.family: root.bar ? root.bar.fontFamily : Style.font.family
                        font.pixelSize: Style.font.iconLarge
                    }
                    Column {
                        anchors.left: parent.left
                        anchors.leftMargin: Style.space(48)
                        anchors.right: remapToggle.left
                        anchors.rightMargin: Style.space(12)
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Style.space(2)
                        Text {
                            text: "Swap CapsLock and Left Ctrl"
                            color: root.barForeground
                            font.family: root.bar ? root.bar.fontFamily : Style.font.family
                            font.pixelSize: Style.font.body
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        Text {
                            text: (root.enabled_ ? "Hardware remap is active" : "Using the default keyboard mapping").toUpperCase()
                            color: Color.muted
                            font.family: root.bar ? root.bar.fontFamily : Style.font.family
                            font.pixelSize: Style.font.caption
                            font.bold: true
                            font.letterSpacing: 1.0
                            elide: Text.ElideRight
                        }
                    }
                    ToggleSwitch {
                        id: remapToggle
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        checked: root.enabled_
                        busy: root.loading
                        foreground: root.barForeground
                        onToggled: root.setSwap(!root.enabled_)
                    }
                }

                Item {
                    width: parent.width
                    height: Style.space(40)

                    Text {
                        width: Style.space(32)
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        text: "󰍬"
                        color: root.barForeground
                        horizontalAlignment: Text.AlignHCenter
                        font.family: root.bar ? root.bar.fontFamily : Style.font.family
                        font.pixelSize: Style.font.iconLarge
                    }
                    Column {
                        anchors.left: parent.left
                        anchors.leftMargin: Style.space(48)
                        anchors.right: voiceToggle.left
                        anchors.rightMargin: Style.space(12)
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Style.space(2)
                        Text {
                            text: "CapsLock dictation"
                            color: root.barForeground
                            font.family: root.bar ? root.bar.fontFamily : Style.font.family
                            font.pixelSize: Style.font.body
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        Text {
                            text: "Tap the CapsLock-position key to toggle Voxtype".toUpperCase()
                            color: Color.muted
                            font.family: root.bar ? root.bar.fontFamily : Style.font.family
                            font.pixelSize: Style.font.caption
                            font.bold: true
                            font.letterSpacing: 1.0
                            elide: Text.ElideRight
                        }
                    }
                    ToggleSwitch {
                        id: voiceToggle
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        checked: root.voiceEnabled_
                        busy: root.loading && root.operation === "voice"
                        foreground: root.barForeground
                        onToggled: root.setVoice(!root.voiceEnabled_)
                    }
                }

                Text {
                    width: parent.width
                    text: root.loading ? "Applying…"
                        : (root.statusText !== "" ? root.statusText
                            : (root.enabled_ ? "keyd is active." : "keyd remap is disabled."))
                    color: root.statusText !== "" ? Color.accent : Color.muted
                    font.family: root.bar ? root.bar.fontFamily : Style.font.family
                    font.pixelSize: Style.font.caption
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
