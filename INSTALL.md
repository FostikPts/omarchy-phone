# Installing Phone on a fresh machine

The plugin is an Omarchy bar widget plus a CLI. It deliberately installs no
packages and edits no Hyprland configs: those steps are done once, by hand
(steps 2 and 4-5 below).

## One command

```bash
curl -fsSL https://raw.githubusercontent.com/FostikPts/omarchy-phone/main/install.sh | bash
```

The installer adds the packages, the plugin, the CLI symlink, the keybindings
and the scrcpy window rule, reloads the config and finishes with
`omarchy-phone doctor`. It is idempotent — a second run only fills in what is
missing.

The steps below are the same thing by hand, if you prefer to control every edit.

## 1. Packages

```bash
omarchy pkg add android-tools scrcpy
```

- `android-tools` provides `adb`; nothing works without it;
- `scrcpy` is the mirror window itself;
- `python3` runs the window watcher (usually already installed).

## 2. Install the plugin

```bash
omarchy plugin add https://github.com/FostikPts/omarchy-phone.git --enable
```

## 3. CLI on PATH

The widget does not need the symlink (it calls the script from the plugin
folder), but keybindings and the terminal do:

```bash
ln -sf ~/.config/omarchy/plugins/admin.phone/bin/omarchy-phone ~/.local/bin/omarchy-phone
```

## 4. Keybindings — `~/.config/hypr/bindings.lua`

```lua
o.bind("SUPER + SHIFT + P", "Mirror phone", "omarchy-phone mirror")
o.bind("SUPER + SHIFT + U", "Phone over USB", "omarchy-phone usb")
o.bind("SUPER + SHIFT + R", "Rotate mirror view", "omarchy-phone view")
```

## 5. Window rule — `~/.config/hypr/windows.lua`

Without it the mirror window tiles and does not follow the phone when it
rotates.

```lua
o.window("^scrcpy$", {
  float = true,
  center = true,
  border_size = 0,
  rounding = 0,
  no_shadow = true,
  no_blur = true,
  tag = "-default-opacity",
})
```

## 6. Apply and check

```bash
hyprctl reload && omarchy restart shell
omarchy-phone doctor
```

`doctor` lists everything that matters and marks problems with `[FAIL]`. If it
ends with `No hard problems found`, the installation is fine.

## The phone does not connect

**The plugin assumes the phone serves the hotspot**, so the phone is the default
gateway. If the phone sits on the same Wi-Fi as the computer instead, the
address cannot be detected automatically.

- Same Wi-Fi: enable Wireless debugging on the phone and run
  `omarchy-phone pair` (Android 11+), then `omarchy-phone mirror`.
- First time is easiest over a cable: `omarchy-phone usb` turns on ADB over Wi-Fi.
- `adb devices` shows `unauthorized` — unlock the phone and tap "Allow debugging".
- `adb devices` is empty — check that ADB over Wi-Fi is enabled and that the
  phone and the computer share a network (or the phone hotspot is on).

## Uninstall

```bash
omarchy plugin disable admin.phone
rm -rf ~/.config/omarchy/plugins/admin.phone ~/.local/state/omarchy-phone
rm -f ~/.local/bin/omarchy-phone
```
