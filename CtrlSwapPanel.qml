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
    property bool voiceCapslockEnabled_: false
    property bool voiceLeftControlEnabled_: false
    property bool voiceRightControlEnabled_: false
    property bool remapApplied_: true
    property string optionsText: ""
    property string statusText: ""
    property string operation: ""
    property string pendingVoiceKey: ""
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
    property var keydConfigOptions: []
    property string selectedKeydConfig: ""
    readonly property color panelForeground: Color.popups.text
    readonly property color panelBackground: Color.popups.background
    readonly property color panelMuted: Util.alpha(Color.popups.text, 0.58)

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
            root.voiceCapslockEnabled_ = data.voiceCapslockEnabled === true;
            root.voiceLeftControlEnabled_ = data.voiceLeftControlEnabled === true;
            root.voiceRightControlEnabled_ = data.voiceRightControlEnabled === true;
            root.selectedKeydConfig = data.selectedKeydConfig || "";
            var configOptions = [];
            var configs = Array.isArray(data.keydConfigs) ? data.keydConfigs : [];
            for (var c = 0; c < configs.length; c++) {
                configOptions.push({
                    value: String(configs[c].path || ""),
                    label: String(configs[c].label || configs[c].name || configs[c].path || "")
                });
            }
            root.keydConfigOptions = configOptions;
            keydConfigDropdown.value = root.selectedKeydConfig;
            root.optionsText = data.options || "";
            root.remapApplied_ = data.remapApplied !== false;
            if (data.remapApplied === false) {
                root.statusText = (root.enabled_ || root.voiceEnabled_)
                    ? "keyd is not running the expected mapping. Toggle a switch once to repair."
                    : "A stale keyd mapping is still active. Toggle a switch once or re-login to repair.";
            }
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
            : (root.voiceEnabled_
                ? "Updating the hardware remap… Authentication may be requested."
                : "Removing the hardware remap… Authentication may be requested.");
        writeProcess.running = true;
    }

    function voiceEnabledFor(key) {
        if (key === "capslock") return root.voiceCapslockEnabled_;
        if (key === "leftcontrol") return root.voiceLeftControlEnabled_;
        if (key === "rightcontrol") return root.voiceRightControlEnabled_;
        return false;
    }

    function setVoice(key, on) {
        if (writeProcess.running) return;
        writeProcess.command = ["python3", root.swapTool, on ? "voice-enable" : "voice-disable", key];
        root.loading = true;
        root.operation = "voice";
        root.pendingVoiceKey = key;
        root.statusText = on
            ? "Enabling " + key + " dictation… Authentication may be requested."
            : "Disabling " + key + " dictation… Authentication may be requested.";
        writeProcess.running = true;
    }

    function setKeydConfig(path) {
        if (writeProcess.running || path === "") return;
        writeProcess.command = ["python3", root.swapTool, "select-keyd-config", path];
        root.loading = true;
        root.operation = "config";
        root.statusText = "Selecting keyboard keyd configuration…";
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
                        ? "Dictation key settings updated."
                        : (root.operation === "config"
                            ? "Keyboard keyd configuration selected."
                        : (root.enabled_
                            ? (root.voiceEnabled_
                                ? "Hardware Ctrl swap is active. Tap CapsLock or Ctrl for dictation; hold either for Ctrl."
                                : "Hardware Ctrl swap is active.")
                            : (root.voiceEnabled_
                                ? "Ctrl swap is off. CapsLock/Ctrl dictation is still active."
                                : "The original key mapping is restored.")));
                }
                root.operation = "";
                root.pendingVoiceKey = "";
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
                    foreground: root.panelForeground
                    background: root.panelBackground
                    accent: Color.accent
                    onChanged: function(value) { root.setInputSchema(value); }
                }

                KeyboardDropdown {
                    id: keyboardLayoutDropdown
                    width: parent.width
                    label: "Keyboard Layout"
                    value: root.currentKeyboardLayout
                    options: root.keyboardLayoutOptions
                    foreground: root.panelForeground
                    background: root.panelBackground
                    accent: Color.accent
                    onChanged: function(value) { root.setKeyboardLayout(value); }
                }

                KeyboardDropdown {
                    id: keydConfigDropdown
                    width: parent.width
                    label: "Keyboard keyd configuration"
                    value: root.selectedKeydConfig
                    options: root.keydConfigOptions
                    foreground: root.panelForeground
                    background: root.panelBackground
                    accent: Color.accent
                    onChanged: function(value) { root.setKeydConfig(value); }
                }

                Item {
                    width: parent.width
                    height: Style.space(40)

                    Text {
                        width: Style.space(32)
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        text: "󰌌"
                        color: root.panelForeground
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
                            color: root.panelForeground
                            font.family: root.bar ? root.bar.fontFamily : Style.font.family
                            font.pixelSize: Style.font.body
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        Text {
                            text: (root.enabled_
                                ? "Hardware remap is active"
                                : (root.voiceEnabled_ ? "Default Ctrl · CapsLock runs dictation" : "Using the default keyboard mapping")).toUpperCase()
                            color: root.panelMuted
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
                        busy: root.loading && root.operation === "swap"
                        foreground: root.panelForeground
                        onToggled: root.setSwap(!root.enabled_)
                    }
                }

                Column {
                    width: parent.width
                    spacing: Style.space(6)
                    Repeater {
                        model: [
                            { key: "capslock", title: "CapsLock dictation" },
                            { key: "leftcontrol", title: "Left Ctrl dictation" },
                            { key: "rightcontrol", title: "Right Ctrl dictation" }
                        ]
                        delegate: Item {
                            required property var modelData
                            width: parent.width
                            height: Style.space(40)

                            Text {
                                width: Style.space(32)
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                text: "󰍬"
                                color: root.panelForeground
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
                                    text: modelData.title
                                    color: root.panelForeground
                                    font.family: root.bar ? root.bar.fontFamily : Style.font.family
                                    font.pixelSize: Style.font.body
                                    font.bold: true
                                    elide: Text.ElideRight
                                }
                                Text {
                                    text: root.voiceEnabledFor(modelData.key)
                                        ? "Press alone to toggle Voxtype; Ctrl shortcuts remain available"
                                        : "Dictation is off"
                                    color: root.panelMuted
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
                                checked: root.voiceEnabledFor(modelData.key)
                                busy: root.loading && root.operation === "voice" && root.pendingVoiceKey === modelData.key
                                foreground: root.panelForeground
                                onToggled: root.setVoice(modelData.key, !root.voiceEnabledFor(modelData.key))
                            }
                        }
                    }
                }

                Text {
                    width: parent.width
                    text: root.loading ? "Applying…"
                        : (root.statusText !== "" ? root.statusText
                            : (!root.remapApplied_ ? "keyd does not match the selected state."
                                : ((root.enabled_ || root.voiceEnabled_) ? "keyd is active." : "keyd is passing keys through.")))
                    color: root.statusText !== "" ? Color.accent : root.panelMuted
                    font.family: root.bar ? root.bar.fontFamily : Style.font.family
                    font.pixelSize: Style.font.caption
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
