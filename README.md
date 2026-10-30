# Phone — ADB + scrcpy for Omarchy

Bar widget and CLI for mirroring an Android phone over Wi-Fi. The phone serves
the hotspot, so its IP is the gateway of the default route — the same address
`ip route | grep default` prints. The plugin re-reads it on every run, so
toggling the hotspot (and the new IP that comes with it) needs no manual step.

## Install

One command (installs packages, the plugin, the CLI symlink, the keybindings
and the window rule, then checks everything):

```bash
curl -fsSL https://raw.githubusercontent.com/FostikPts/omarchy-phone/main/install.sh | bash
```

Or do it by hand — see [INSTALL.md](INSTALL.md). Short version:

```bash
omarchy pkg add android-tools scrcpy
omarchy plugin add https://github.com/FostikPts/omarchy-phone.git --enable
ln -sf ~/.config/omarchy/plugins/admin.phone/bin/omarchy-phone ~/.local/bin/omarchy-phone
```

Then add the keybinding and the scrcpy window rule (INSTALL.md, steps 4-5) and
check everything at once:

```bash
omarchy-phone doctor
```

**The plugin assumes the phone serves the hotspot** (the phone is the default
gateway). If the phone is on the same Wi-Fi as the computer instead, pair once:
`omarchy-phone pair`, then `omarchy-phone mirror`.

## Layout

```
~/.config/omarchy/plugins/admin.phone/
├── manifest.json        # bar widget manifest
├── Panel.qml            # bar icon + popup panel
├── Model.js             # status parsing, labels, action list
└── bin/
    ├── omarchy-phone    # the CLI (symlinked to ~/.local/bin/omarchy-phone)
    └── phone-watch.py   # re-fits the scrcpy window when the phone rotates
```

## CLI

```bash
omarchy-phone ip                # detected phone IP (default-route gateway)
omarchy-phone ip --notify       # same, as a notification
omarchy-phone status [--json]   # state for scripts and the widget
omarchy-phone doctor             # check deps, keybinding, network, phone
omarchy-phone connect           # ADB over Wi-Fi
omarchy-phone disconnect        # drop Wi-Fi ADB connections
omarchy-phone mirror            # connect if needed, then scrcpy
omarchy-phone rotate            # toggle portrait/landscape (locks rotation)
omarchy-phone rotate portrait   # force portrait
omarchy-phone rotate landscape  # force landscape
omarchy-phone rotate auto       # follow the phone accelerometer again
omarchy-phone usb               # one-time: adb tcpip 5555 over the USB cable
omarchy-phone pair [addr] [code]  # Android 11+ Wireless debugging
omarchy-phone auto              # silent reconnect (widget + post-boot hook)
```

`connect` tries, in order:

1. an address already online in `adb devices`
2. an mDNS service for the gateway (Android 11+ Wireless debugging)
3. the classic `5555` port
4. `adb tcpip 5555` over USB, when the cable is plugged in

The first run on a new phone needs one of the two one-time setups:

- **USB:** plug in the cable, allow USB debugging, then `omarchy-phone usb`
- **Wireless debugging (Android 11+):** enable it on the phone, then
  `omarchy-phone pair` (the menu row opens a terminal for the pairing code)

## Mirror window and rotation

The scrcpy window is borderless, floating and centred (window rules for class
`^scrcpy$` in `~/.config/hypr/windows.lua`). It is sized to the phone screen:
the phone decides the aspect ratio, the plugin makes the window match it.

Neither Wayland nor Hyprland lets a client resize or rotate its own window, so
`mirror` starts `bin/phone-watch.py`. It polls the mirrored display and, when
the phone rotates, asks Hyprland (`hyprctl`) to resize and re-centre the scrcpy
window. The window follows both a physical rotation (with auto-rotate on) and a
manual `rotate`, usually within a second.

`omarchy-phone rotate` locks the orientation the same way a rotation lock does:
it switches between portrait and landscape. It also tells Android to ignore
app orientation requests during that rotation, so it works on portrait-only
screens such as the launcher. `omarchy-phone rotate auto` hands control back to
the accelerometer and to the apps.

The phone screen stays on while mirroring (`--stay-awake`, no
`--turn-screen-off`), otherwise it would stop following the accelerometer.

## Bar widget

- Left click: panel with IP, ADB state, device model and actions, including
  Rotate phone screen and Follow phone rotation
- Right click: mirror immediately
- Dim icon: not connected
- The widget polls status every 15 s and reconnects a known phone after the
  hotspot IP changes (disable with `"autoReconnect": false` in the widget's
  `shell.json` entry).

## Menu

`SUPER + SPACE` → search "phone": Mirror screen / Rotate screen / Follow phone
rotation / Connect / Disconnect / Show IP / Pair.

## Keybinding

| Key | Command |
|---|---|
| `SUPER + SHIFT + P` | `omarchy-phone mirror` — connect and mirror |
| `SUPER + SHIFT + U` | `omarchy-phone usb` — enable ADB over Wi-Fi using the USB cable |
| `SUPER + SHIFT + R` | `omarchy-phone view` — turn the mirror image by 90° |

All three report through desktop notifications, so they work without a
terminal. The Google Photos webapp binding lives on `SUPER + ALT + P`.

`mirror` already bootstraps over USB on its own: if the phone is plugged in
and not reachable over Wi-Fi yet, it runs `adb tcpip 5555` first. The `U` key
is for doing only that step, e.g. to enable Wi-Fi ADB once and then unplug.

## Config

`~/.config/omarchy-phone/config` (optional, `KEY=value`):

```bash
ADB_PORT=5555                                    # classic wireless adb port
PHONE_IFACE=""                                   # force an interface (e.g. wlp3s0)
SCRCPY_ARGS="--stay-awake --window-title=Phone --window-borderless --shortcut-mod=lctrl"
AUTO_RECONNECT=1                                 # 0 disables `omarchy-phone auto`
NOTIFY=1                                         # 0 disables notifications
```

`PHONE_IFACE` is only needed when several default routes exist and the
automatic wireless-interface preference picks the wrong one (an unusual VPN
setup).

State lives in `~/.local/state/omarchy-phone/` (`state`, `phone.log`).
`omarchy-phone disconnect` clears the state, which also stops auto-reconnect
until the next manual connect.

## Uninstall

```bash
omarchy plugin remove admin.phone
rm ~/.local/bin/omarchy-phone
rm -rf ~/.local/state/omarchy-phone ~/.config/omarchy-phone
rm ~/.config/omarchy/hooks/post-boot.d/omarchy-phone-auto
```

## View rotation (image only)

`omarchy-phone view [0|90|180|270]` turns the **mirror image** inside the scrcpy
window and leaves the phone alone — unlike `rotate`, which changes the Android
screen rotation, and unlike moving the phone, which changes what the camera and
apps see.

With no argument it advances by 90° (`0 → 90 → 180 → 270 → 0`). The angle is
remembered in `~/.local/state/omarchy-phone/view` and reused by every later
`mirror`. Because scrcpy reads the orientation only at start-up, changing it
while mirroring recreates the window; the window watcher is told the angle too,
so it keeps the window fitted to the rotated image.

Key: `SUPER + SHIFT + R` (`o.bind` in `~/.config/hypr/bindings.lua`).
The widget panel shows the four presets as one row of chips (0°, 90°, 180°,
270°); the current angle is drawn pressed and cannot be applied again.

In the panel the keyboard reaches the chips as well: `↓` walks the action
rows and then enters the preset row, `←`/`→` pick a preset, `↑` goes
back, `Enter` applies the focused one.

## Live state in the panel

Two rows reflect the phone instead of being plain commands:

- **Mirror screen** is highlighted while scrcpy runs and shows the
  workspace the window sits on (`workspace 4`).
- **Follow phone rotation** is highlighted while the phone follows its
  accelerometer (`on`). Pressing it again locks the phone at its current
  rotation (`off`) instead of leaving auto-rotate on — `wm user-rotation
  lock` without an angle keeps the orientation it has right now.

Command line: `scrcpy --display-orientation=<angle>`.
