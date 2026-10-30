import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "Model.js" as Model

// Phone: ADB over Wi-Fi + scrcpy.
//
// The phone IP is never stored here — the CLI re-reads the default route every
// time, so toggling the hotspot (and getting a new address) just works.
Panel {
  id: root

  moduleName: "admin.phone"
  ipcTarget: "admin.phone"
  // manageIpc: false so this panel can own the single IpcHandler the target
  // allows — needed for the connect/disconnect/mirror actions below.
  manageIpc: false

  // The CLI ships inside the plugin folder, so the widget works even if the
  // ~/.local/bin symlink is missing. That symlink exists for terminal use.
  readonly property string cliPath: String(Qt.resolvedUrl("bin/omarchy-phone")).replace("file://", "")

  readonly property color foreground: bar ? bar.foreground : Commons.Color.foreground
  readonly property color urgent: bar ? bar.urgent : Commons.Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.6)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property bool autoReconnect: setting("autoReconnect", true)

  property var status: Model.emptyStatus()
  property var actions: Model.actionsFor(status)
  property var viewPresets: Model.viewPresets(status)
  property bool chipsFocused: false
  property int chipIndex: 0
  property bool busy: false
  property string flash: ""
  property int selectedIndex: 0
  property bool cursorActive: false

  readonly property bool connected: status.connected === true

  function refresh() {
    if (!statusProc.running) statusProc.running = true
  }

  function applyStatus(raw) {
    var wasConnected = root.connected
    var parsed = Model.parseStatus(raw)
    root.status = parsed
    if (root.selectedIndex > root.actions.length - 1)
      root.selectedIndex = Math.max(0, root.actions.length - 1)
    if (parsed.connected && !wasConnected)
      root.flash = "Connected to " + parsed.serial
    else if (!parsed.connected && wasConnected)
      root.flash = ""
  }

  // Reconnect by itself when the hotspot was toggled and the IP moved. Only
  // phones seen before are reconnected (the CLI keeps that in its state file),
  // so sitting on a hotel/office Wi-Fi never pokes random gateways.
  function maybeAuto() {
    if (root.busy || autoProc.running) return
    if (!root.autoReconnect) return
    if (root.status.connected || !root.status.hasState) return
    if (!root.status.adb || !root.status.ip) return
    autoProc.running = true
  }

  function activeChipIndex() {
    for (var i = 0; i < root.viewPresets.length; i++)
      if (root.viewPresets[i].active) return i
    return 0
  }

  function moveCursor(delta) {
    if (root.actions.length === 0) {
      root.cursorActive = true
      root.chipsFocused = root.viewPresets.length > 0
      return
    }
    root.cursorActive = true
    if (root.chipsFocused) {
      root.chipsFocused = false
      root.selectedIndex = delta > 0 ? 0 : Math.max(0, root.actions.length - 1)
      return
    }
    var next = root.selectedIndex + delta
    if (delta > 0 && next > root.actions.length - 1) {
      root.chipsFocused = true
      root.chipIndex = root.activeChipIndex()
      return
    }
    if (next < 0) next = root.actions.length - 1
    if (next > root.actions.length - 1) next = 0
    root.selectedIndex = next
  }

  function moveChip(delta) {
    if (!root.chipsFocused || root.viewPresets.length === 0) return false
    var next = root.chipIndex + delta
    if (next < 0) next = root.viewPresets.length - 1
    if (next > root.viewPresets.length - 1) next = 0
    root.chipIndex = next
    return true
  }

  function activateSelected() {
    if (root.chipsFocused) {
      var preset = root.viewPresets[root.chipIndex]
      if (preset && !preset.active) root.runView(preset.angle)
      return
    }
    var action = root.actions[root.selectedIndex]
    if (!action || action.enabled === false) return
    root.runAction(action.id)
  }

  function runView(angle) {
    if (root.busy) return
    if (Number(root.status.view) === Number(angle)) return
    root.busy = true
    root.flash = ""
    actionProc.command = [root.cliPath, "view", String(angle)]
    actionProc.running = true
  }

  function runAction(id) {
    if (id === "help" || root.busy) return

    if (id === "pair") {
      // Pairing needs the code typed in, so hand off to a terminal.
      Quickshell.execDetached(["omarchy-launch-terminal", "omarchy-phone", "pair"])
      root.close()
      return
    }

    if (id === "refresh") {
      root.flash = ""
      root.refresh()
      return
    }

    var action = null
    for (var i = 0; i < root.actions.length; i++) {
      if (root.actions[i].id === id) {
        action = root.actions[i]
        break
      }
    }

    var command = [root.cliPath]
    var args = action && action.args ? action.args : [id]
    for (var j = 0; j < args.length; j++) command.push(args[j])

    root.busy = true
    root.flash = ""
    actionProc.command = command
    actionProc.running = true
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Component.onCompleted: refresh()

  onOpenedChanged: {
    if (opened) {
      root.cursorActive = false
      root.chipsFocused = false
      root.flash = ""
      root.refresh()
    }
  }

  Timer {
    interval: 15000
    repeat: true
    running: true
    onTriggered: root.refresh()
  }

  Timer {
    interval: 20000
    repeat: true
    running: true
    onTriggered: root.maybeAuto()
  }

  Process {
    id: statusProc
    command: [root.cliPath, "status", "--json"]
    stdout: StdioCollector {
      id: statusOut
      waitForEnd: true
      onStreamFinished: root.applyStatus(statusOut.text)
    }
  }

  Process {
    id: actionProc
    stdout: StdioCollector { id: actionOut; waitForEnd: true }
    stderr: StdioCollector { id: actionErr; waitForEnd: true }
    onExited: function(code) {
      root.busy = false
      var out = String(actionOut.text || "").trim()
      var err = String(actionErr.text || "").trim()
      if (code === 0) root.flash = out.split("\n")[0]
      else root.flash = err !== "" ? err.replace(/^omarchy-phone: /, "") : "Command failed"
      root.refresh()
    }
  }

  Process {
    id: autoProc
    command: [root.cliPath, "auto"]
    stdout: StdioCollector { waitForEnd: true }
    onExited: root.refresh()
  }

  IpcHandler {
    target: "admin.phone"

    function open() { root.open() }
    function close() { root.close() }
    function show() { root.open() }
    function hide() { root.close() }
    function toggle() { root.toggle() }
    function refresh() { root.refresh() }
    function state(): string { return JSON.stringify(root.status) }
    function cursorState(): string { return JSON.stringify({ active: root.cursorActive, chips: root.chipsFocused, chip: root.chipIndex, row: root.selectedIndex, actions: root.actions.length }) }
    function connect() { root.runAction("connect") }
    function disconnect() { root.runAction("disconnect") }
    function mirror() { root.runAction("mirror") }
    function rotate() { root.runAction("rotate") }
    function view() { root.runAction("view") }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: Model.barGlyph(root.status)
    active: root.connected
    activeColor: Commons.Color.accent
    dimmed: !root.connected && !root.busy
    tooltipText: Model.tooltip(root.status, root.busy)

    onPressed: function(b) {
      if (b === Qt.RightButton) root.runAction("mirror")
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(400))
    contentHeight: panel.fittedContentHeight(panelColumn.implicitHeight, Style.space(560))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent

      onMoveRequested: function(dx, dy) {
        if (dx !== 0 && root.moveChip(dx)) return
        if (dy !== 0) root.moveCursor(dy)
      }
      onActivateRequested: {
        root.cursorActive = true
        root.activateSelected()
      }
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: panelColumn
        width: parent.width
        spacing: Style.space(14)

        PanelHero {
          width: parent.width
          title: "Phone"
          meta: Model.heroMeta(root.status)
          foreground: root.foreground
          fontFamily: root.fontFamily
          iconComponent: Component {
            Text {
              text: Model.barGlyph(root.status)
              color: root.connected ? Commons.Color.accent : root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.display
            }
          }
        }

        PanelSeparator { foreground: root.foreground }

        Column {
          width: parent.width
          spacing: Style.space(6)

          PanelSectionHeader {
            text: "CONNECTION"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          InfoRow {
            label: "Phone IP"
            value: root.status.ip !== ""
              ? root.status.ip + (root.status.iface !== "" ? " · " + root.status.iface : "")
              : "—"
          }

          InfoRow {
            label: "ADB"
            value: Model.adbLabel(root.status)
          }

          InfoRow {
            visible: root.status.model !== ""
            label: "Device"
            value: root.status.model
          }
        }

        PanelSeparator { foreground: root.foreground }

        Column {
          width: parent.width
          spacing: Style.space(6)

          PanelSectionHeader {
            text: "ACTIONS"
            foreground: root.foreground
            fontFamily: root.fontFamily
          }

          Repeater {
            model: root.actions

            ActionRow {
              required property var modelData
              required property int index
              action: modelData
              rowIndex: index
            }
          }

          Row {
            width: parent.width
            spacing: Style.space(6)

            Repeater {
              model: root.viewPresets

              ViewPresetButton {
                required property var modelData
                required property int index
                preset: modelData
                slot: index
              }
            }
          }
        }

        Text {
          width: parent.width
          textFormat: Text.PlainText
          text: root.busy ? "Working…" : (root.flash !== "" ? root.flash : Model.hint(root.status))
          color: root.busy || root.flash === "" ? root.dim : root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }

        Item {
          width: parent.width
          height: Style.space(2)
        }
      }
    }
  }

  component InfoRow: Item {
    id: infoRow
    property string label: ""
    property string value: ""

    width: parent ? parent.width : implicitWidth
    implicitHeight: Math.max(labelText.implicitHeight, valueText.implicitHeight) + Style.space(4)

    Text {
      id: labelText
      text: infoRow.label
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      anchors.left: parent.left
      anchors.leftMargin: Style.space(8)
      anchors.verticalCenter: parent.verticalCenter
    }

    Text {
      id: valueText
      textFormat: Text.PlainText
      text: infoRow.value
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      elide: Text.ElideMiddle
      horizontalAlignment: Text.AlignRight
      anchors.right: parent.right
      anchors.rightMargin: Style.space(8)
      anchors.verticalCenter: parent.verticalCenter
      width: Math.max(0, infoRow.width - labelText.implicitWidth - Style.space(32))
    }
  }

  component ViewPresetButton: Rectangle {
    id: presetButton
    required property var preset
    property int slot: 0

    readonly property bool hasCursor: root.cursorActive && root.chipsFocused && root.chipIndex === presetButton.slot
    readonly property bool current: preset !== undefined && preset !== null && preset.active === true
    readonly property bool usable: preset !== undefined && preset !== null && !preset.active && !root.busy

    width: parent ? Math.max(0, (parent.width - parent.spacing * 3) / 4) : Style.space(80)
    height: Style.space(30)
    radius: Style.space(4)
    color: current ? Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.16) : "transparent"
    border.width: presetButton.hasCursor ? 2 : 1
    border.color: (current || presetButton.hasCursor) ? Commons.Color.accent : root.dim
    opacity: current ? 1.0 : (usable ? 1.0 : 0.6)

    Text {
      anchors.centerIn: parent
      text: presetButton.preset ? presetButton.preset.label : ""
      color: presetButton.current ? Commons.Color.accent : root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
    }

    MouseArea {
      anchors.fill: parent
      enabled: presetButton.usable
      hoverEnabled: true
      cursorShape: presetButton.usable ? Qt.PointingHandCursor : Qt.ArrowCursor
      onContainsMouseChanged: if (containsMouse) {
        root.cursorActive = true
        root.chipsFocused = true
        root.chipIndex = presetButton.slot
      }
      onClicked: if (presetButton.usable) root.runView(presetButton.preset.angle)
    }
  }

  component ActionRow: CursorSurface {
    id: row
    required property var action
    required property int rowIndex

    readonly property bool activeRow: root.cursorActive && root.selectedIndex === rowIndex
    readonly property bool usable: action !== undefined && action !== null && action.enabled !== false
    readonly property bool lit: row.action !== undefined && row.action !== null && row.action.active === true

    width: parent ? parent.width : implicitWidth
    implicitHeight: Math.max(rowGlyph.implicitHeight, rowLabel.implicitHeight, rowHint.implicitHeight) + Style.space(12)
    hasCursor: activeRow
    foreground: root.foreground
    opacity: usable ? 1.0 : 0.5

    Text {
      id: rowGlyph
      text: row.action ? row.action.glyph : ""
      color: row.lit ? Commons.Color.accent : ((row.action && row.action.danger) ? root.urgent : root.foreground)
      font.family: root.fontFamily
      font.pixelSize: Style.font.title
      anchors.left: parent.left
      anchors.leftMargin: Style.space(8)
      anchors.verticalCenter: parent.verticalCenter
    }

    Text {
      id: rowHint
      textFormat: Text.PlainText
      text: row.action && row.action.hint ? row.action.hint : ""
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      elide: Text.ElideRight
      horizontalAlignment: Text.AlignRight
      width: Math.min(implicitWidth, Style.space(160))
      anchors.right: parent.right
      anchors.rightMargin: Style.space(8)
      anchors.verticalCenter: parent.verticalCenter
    }

    Text {
      id: rowLabel
      textFormat: Text.PlainText
      text: row.action ? row.action.label : ""
      color: row.lit ? Commons.Color.accent : root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      elide: Text.ElideRight
      anchors.left: rowGlyph.right
      anchors.leftMargin: Style.space(10)
      anchors.right: rowHint.left
      anchors.rightMargin: Style.space(8)
      anchors.verticalCenter: parent.verticalCenter
    }

    MouseArea {
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: row.usable ? Qt.PointingHandCursor : Qt.ArrowCursor
      onContainsMouseChanged: if (containsMouse && row.usable) {
        root.cursorActive = true
        root.selectedIndex = row.rowIndex
      }
      onClicked: if (row.usable) root.runAction(row.action.id)
    }
  }
}
