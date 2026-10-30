#!/usr/bin/env bash
# One-shot installer for the Phone plugin for Omarchy.
#
#   curl -fsSL https://raw.githubusercontent.com/FostikPts/omarchy-phone/main/install.sh | bash
#
# It is idempotent: running it again only fills in what is missing.
set -uo pipefail

REPO="https://github.com/FostikPts/omarchy-phone.git"
PLUGIN_ID="admin.phone"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
PLUGIN_DIR="$CONFIG_DIR/omarchy/plugins/$PLUGIN_ID"
BINDINGS="$CONFIG_DIR/hypr/bindings.lua"
WINDOWS="$CONFIG_DIR/hypr/windows.lua"
CLI="$HOME/.local/bin/omarchy-phone"

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mwarn\033[0m %s\n' "$*"; }

if ! command -v omarchy >/dev/null 2>&1; then
  echo "omarchy not found — this installer is for Omarchy (Arch-based) only" >&2
  exit 1
fi

# 1. packages
if command -v adb >/dev/null 2>&1 && command -v scrcpy >/dev/null 2>&1; then
  say "adb and scrcpy are already installed"
else
  say "Installing android-tools and scrcpy"
  omarchy pkg add android-tools scrcpy || {
    echo "could not install the packages — run: omarchy pkg add android-tools scrcpy" >&2
    exit 1
  }
fi

# 2. plugin
if [ -d "$PLUGIN_DIR/.git" ]; then
  say "Plugin already present — updating"
  git -C "$PLUGIN_DIR" pull --ff-only >/dev/null 2>&1 || warn "git pull failed (local changes?), keeping the current copy"
  omarchy plugin enable "$PLUGIN_ID" >/dev/null 2>&1 || warn "could not enable $PLUGIN_ID"
elif [ -d "$PLUGIN_DIR" ]; then
  say "Plugin directory exists without git — leaving it alone"
  omarchy plugin enable "$PLUGIN_ID" >/dev/null 2>&1 || true
else
  say "Installing the plugin from $REPO"
  omarchy plugin add "$REPO" --enable || {
    echo "plugin install failed" >&2
    exit 1
  }
fi

# 3. CLI symlink
if [ -x "$PLUGIN_DIR/bin/omarchy-phone" ]; then
  mkdir -p "$HOME/.local/bin"
  ln -sf "$PLUGIN_DIR/bin/omarchy-phone" "$CLI"
  say "CLI: $CLI"
else
  warn "bin/omarchy-phone not found in $PLUGIN_DIR"
fi

# 4. keybindings
if [ -f "$BINDINGS" ]; then
  changed=0
  add_bind() {
    if grep -qF "$1" "$BINDINGS" 2>/dev/null; then
      return 0
    fi
    printf '%s\n' "$2" >>"$BINDINGS"
    changed=$((changed + 1))
  }
  add_bind 'omarchy-phone mirror' 'o.bind("SUPER + SHIFT + P", "Mirror phone", "omarchy-phone mirror")'
  add_bind 'omarchy-phone usb'    'o.bind("SUPER + SHIFT + U", "Phone over USB", "omarchy-phone usb")'
  add_bind 'omarchy-phone view'   'o.bind("SUPER + SHIFT + R", "Rotate mirror view", "omarchy-phone view")'
  if ((changed)); then
    say "Added $changed keybinding(s) to bindings.lua"
  else
    say "Keybindings already present"
  fi
else
  warn "no $BINDINGS — add the keybindings yourself (see INSTALL.md)"
fi

# 5. scrcpy window rule
if [ -f "$WINDOWS" ]; then
  if grep -q '\^scrcpy\$' "$WINDOWS" 2>/dev/null; then
    say "scrcpy window rule already present"
  else
    cat >>"$WINDOWS" <<'LUA'

-- scrcpy (phone mirroring, launched by `omarchy-phone mirror`): frameless
-- floating window, so it follows the phone when it rotates.
o.window("^scrcpy$", {
  float = true,
  center = true,
  border_size = 0,
  rounding = 0,
  no_shadow = true,
  no_blur = true,
  tag = "-default-opacity",
})
LUA
    say "Added the scrcpy window rule to windows.lua"
  fi
else
  warn "no $WINDOWS — add the window rule yourself (see INSTALL.md)"
fi

# 6. reload
say "Reloading Hyprland and the shell"
hyprctl reload >/dev/null 2>&1 || warn "hyprctl reload failed"
omarchy restart shell >/dev/null 2>&1 || warn "could not restart the shell"

# 7. check
if [ -x "$CLI" ]; then
  echo
  "$CLI" doctor || true
fi

cat <<'DONE'

Done.
  SUPER + SHIFT + P   mirror the phone
  SUPER + SHIFT + U   enable ADB over Wi-Fi using the USB cable
  SUPER + SHIFT + R   turn the mirror image by 90° (the phone stays as it is)
DONE
