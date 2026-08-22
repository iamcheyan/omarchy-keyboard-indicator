import QtQuick
import QtQuick.Controls
import qs.Commons
import qs.Ui

Item {
    id: root

    property string label: ""
    property string value: ""
    property var options: []
    property color foreground: Color.popups.text
    property color background: Color.popups.background
    property color accent: Color.accent
    property string fontFamily: Style.font.family
    property int rowHeight: Style.spacing.controlHeight
    property int popupRowHeight: Style.spacing.popupRowHeight
    property bool expanded: false

    signal changed(string value)

    implicitHeight: label !== "" ? rowHeight + Style.spacing.huge : rowHeight

    function optionValue(option) {
        return option && typeof option === "object" ? String(option.value) : String(option)
    }

    function optionLabel(option) {
        return option && typeof option === "object" ? String(option.label) : String(option)
    }

    function currentLabel() {
        for (var i = 0; i < options.length; i++) {
            if (optionValue(options[i]) === value) return optionLabel(options[i])
        }
        return value
    }

    function openMenu() {
        expanded = true
        menu.open()
    }

    function closeMenu() {
        expanded = false
        menu.close()
    }

    Column {
        anchors.fill: parent
        spacing: Style.spacing.labelGap

        Text {
            width: parent.width
            text: root.label
            color: Qt.darker(root.foreground, 1.4)
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
        }

        BorderSurface {
            id: trigger
            width: parent.width
            height: root.rowHeight
            color: Style.controlFill(trigger.activeFocus, triggerHover.hovered, root.foreground, root.accent)
            borderSpec: Border.controlSpec(trigger.activeFocus ? "focus" : (triggerHover.hovered ? "hover" : "normal"), root.foreground, root.accent)
            activeFocusOnTab: true

            HoverHandler {
                id: triggerHover
            }

            Keys.onPressed: function(event) {
                if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter
                        || event.key === Qt.Key_Space || event.key === Qt.Key_Down) {
                    root.expanded ? root.closeMenu() : root.openMenu()
                    event.accepted = true
                } else if (event.key === Qt.Key_Escape && root.expanded) {
                    root.closeMenu()
                    event.accepted = true
                }
            }

            Text {
                anchors.left: parent.left
                anchors.right: arrow.left
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: trigger.borderLeft + Style.spacing.controlPaddingX
                anchors.rightMargin: Style.spacing.md
                text: root.currentLabel()
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                elide: Text.ElideRight
            }

            Text {
                id: arrow
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.rightMargin: trigger.borderRight + Style.spacing.controlGap
                text: root.expanded ? "󰅃" : "󰅀"
                color: Qt.darker(root.foreground, 1.2)
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    trigger.forceActiveFocus()
                    root.expanded ? root.closeMenu() : root.openMenu()
                }
            }
        }
    }

    Popup {
        id: menu
        x: trigger.x
        y: trigger.y + trigger.height + Style.spacing.xxs
        width: trigger.width
        padding: Style.spacing.hairline
        // The trigger owns the toggle state. CloseOnPressOutside would close
        // during the press event, then the trigger click would open it again.
        closePolicy: Popup.CloseOnEscape
        implicitHeight: Math.min(root.options.length * root.popupRowHeight + Style.spacing.xxs,
                                 root.popupRowHeight * 8 + Style.spacing.xxs)

        background: BorderSurface {
            color: root.background
            borderSpec: Border.localOrSurfaceSpec("popups", "border", Color.popups.border, Color.popups.border, Style.normalBorderWidth)
            radius: Style.cornerRadius
        }

        onOpened: root.expanded = true
        onClosed: root.expanded = false

        contentItem: ListView {
            id: optionList
            model: root.options
            implicitHeight: contentHeight
            spacing: Style.spacing.labelGap
            clip: true

            delegate: Rectangle {
                required property var modelData
                required property int index
                width: optionList.width
                height: root.popupRowHeight
                color: mouse.containsMouse ? Style.hoverFillFor(root.foreground, root.accent) : "transparent"

                Text {
                    anchors.fill: parent
                    anchors.leftMargin: Style.spacing.controlPaddingX
                    anchors.rightMargin: Style.spacing.controlPaddingX
                    verticalAlignment: Text.AlignVCenter
                    text: root.optionLabel(modelData)
                    color: parent.color === "transparent" ? root.foreground : Style.hoverStateColor(root.foreground, root.accent)
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.body
                    elide: Text.ElideRight
                }

                MouseArea {
                    id: mouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.value = root.optionValue(modelData)
                        root.changed(root.value)
                        root.closeMenu()
                    }
                }
            }
        }
    }
}
