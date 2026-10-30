// Pure helpers for the Phone bar widget: status parsing, labels and the action
// list. Nothing here touches QML, so the widget stays mostly declarative.

var GLYPH_PHONE = "\uf011c"    // md-cellphone
var GLYPH_LINKED = "\uf0121"   // md-cellphone-link
var GLYPH_UNLINK = "\uf0122"   // md-cellphone-link-off
var GLYPH_MIRROR = "\uf0989"   // md-monitor-cellphone
var GLYPH_ROTATE = "\uf0475"   // md-screen-rotation
var GLYPH_AUTO = "\uf006a"     // md-autorenew
var GLYPH_USB = "\uf0553"      // md-usb
var GLYPH_KEY = "\uf094e"      // md-cellphone-key
var GLYPH_REFRESH = "\uf0450"  // md-refresh
var GLYPH_ALERT = "\uf05d6"    // md-alert-circle-outline

function emptyStatus() {
  return {
    ip: "",
    iface: "",
    serial: "",
    connected: false,
    state: "disconnected",
    model: "",
    mirroring: false,
    hasState: false,
    adb: true,
    scrcpy: true,
    port: "5555",
    view: 0,
    follow: false,
    workspace: ""
  }
}

function parseStatus(raw) {
  var status = emptyStatus()
  var data = null
  try {
    data = JSON.parse(String(raw || ""))
  } catch (e) {
    data = null
  }
  if (!data || typeof data !== "object") return status

  status.ip = String(data.ip || "")
  status.iface = String(data.iface || "")
  status.serial = String(data.serial || "")
  status.connected = data.connected === true
  status.state = String(data.state || "disconnected")
  status.model = String(data.model || "")
  status.mirroring = data.mirroring === true
  status.hasState = data.hasState === true
  status.adb = data.adb !== false
  status.scrcpy = data.scrcpy !== false
  status.port = String(data.port || "5555")
  status.view = Number(data.view) || 0
  status.follow = data.follow === true
  status.workspace = String(data.workspace || "")
  return status
}

function barGlyph(status) {
  return status.connected ? GLYPH_LINKED : GLYPH_PHONE
}

function tooltip(status, busy) {
  if (busy) return "Phone — working…"
  if (!status.adb) return "Phone — ADB is not installed"
  if (status.connected) return "Phone — " + status.serial
  if (!status.ip) return "Phone — no default route"
  return "Phone — not connected (" + status.ip + ")"
}

function heroMeta(status) {
  if (!status.adb) return "ADB IS NOT INSTALLED"
  if (!status.ip) return "NO DEFAULT ROUTE"
  if (status.connected) return "CONNECTED · " + status.serial
  if (status.state === "unauthorized") return "AUTHORIZE ON PHONE"
  if (status.state === "offline") return "OFFLINE · " + status.ip
  return "NOT CONNECTED · " + status.ip
}

function adbLabel(status) {
  if (!status.adb) return "missing"
  if (status.connected) return status.serial
  if (status.state === "unauthorized") return "unauthorized"
  if (status.state === "offline") return "offline"
  return "not connected"
}

function hint(status) {
  if (!status.adb) return "Install android-tools: omarchy pkg add android-tools"
  if (!status.ip) return "No default route. Turn on the phone hotspot."
  if (status.state === "unauthorized") return "Tap “Allow USB debugging” on the phone."
  if (status.connected && status.mirroring) return "scrcpy is running."
  if (status.connected) return "Right-click the bar icon to mirror immediately."
  return "One-time setup: plug in USB and run omarchy-phone usb, or enable Wireless debugging and run omarchy-phone pair."
}

var VIEW_ANGLES = [0, 90, 180, 270]

// The four view presets: the active one is shown pressed and cannot be
// triggered again, so the row always mirrors the real state.
function viewPresets(status) {
  var current = Number(status && status.view) || 0
  var presets = []
  for (var i = 0; i < VIEW_ANGLES.length; i++) {
    var angle = VIEW_ANGLES[i]
    presets.push({
      angle: angle,
      label: angle + "°",
      active: angle === current
    })
  }
  return presets
}

function actionsFor(status) {
  if (!status.adb) {
    return [{
      id: "help",
      glyph: GLYPH_ALERT,
      label: "ADB is not installed",
      hint: "omarchy pkg add android-tools",
      enabled: false
    }]
  }

  var actions = [{
    id: "mirror",
    glyph: GLYPH_MIRROR,
    label: "Mirror screen",
    hint: status.mirroring
      ? (status.workspace !== "" ? "workspace " + status.workspace : "running")
      : (status.scrcpy ? "scrcpy" : "install scrcpy"),
    enabled: status.scrcpy,
    active: status.mirroring
  }]

  if (status.connected) {
    actions.push({
      id: "rotate",
      glyph: GLYPH_ROTATE,
      label: "Rotate phone screen",
      hint: "portrait ⇄ landscape",
      enabled: true
    })

    actions.push({
      id: "follow",
      glyph: GLYPH_AUTO,
      label: "Follow phone rotation",
      hint: status.follow ? "on" : "off",
      enabled: true,
      active: status.follow,
      args: ["rotate", "follow"]
    })

    actions.push({
      id: "disconnect",
      glyph: GLYPH_UNLINK,
      label: "Disconnect ADB",
      hint: status.serial,
      enabled: true,
      danger: true
    })
  } else {
    actions.push({
      id: "connect",
      glyph: GLYPH_LINKED,
      label: "Connect ADB",
      hint: status.ip || "no route",
      enabled: true
    })
  }

  actions.push({
    id: "usb",
    glyph: GLYPH_USB,
    label: "Enable Wi-Fi ADB over USB",
    hint: "one-time",
    enabled: true
  })

  actions.push({
    id: "pair",
    glyph: GLYPH_KEY,
    label: "Pair with wireless debugging",
    hint: "Android 11+",
    enabled: true
  })

  actions.push({
    id: "refresh",
    glyph: GLYPH_REFRESH,
    label: "Refresh",
    hint: "",
    enabled: true
  })

  return actions
}

if (typeof module !== "undefined") {
  module.exports = {
    emptyStatus: emptyStatus,
    parseStatus: parseStatus,
    barGlyph: barGlyph,
    tooltip: tooltip,
    heroMeta: heroMeta,
    adbLabel: adbLabel,
    hint: hint,
    actionsFor: actionsFor,
    viewPresets: viewPresets
  }
}
