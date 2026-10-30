#!/usr/bin/env python3
"""Keep the scrcpy window fitted to the phone display.

Wayland gives a client no way to resize its own toplevel window, and Hyprland
has no per-window rotation. So when the phone display rotates (or its size
changes), scrcpy's video changes aspect ratio but its window keeps the old
shape. This watcher polls the mirrored display and asks Hyprland (through
hyprctl) to resize and center the scrcpy window around the new video.

It is started by `omarchy-phone mirror` and stops when scrcpy disappears.
`--view` carries the client-side rotation (`omarchy-phone view`), which turns
the image without rotating the phone, so the window keeps fitting.
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time

DISPLAY_MARGIN = 96  # scrcpy leaves this much room around its window
POLL_INTERVAL = 1.0
ASPECT_TOLERANCE = 0.02
MISSING_LIMIT = 5  # consecutive polls without scrcpy before exiting

_stopping = False


def log(message):
    sys.stderr.write("%s phone-watch: %s\n" % (time.strftime("%F %T"), message))
    sys.stderr.flush()


def run(args, timeout=12):
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.SubprocessError):
        return None


def display_size(serial):
    """Return (width, height) of display 0, the phone screen scrcpy mirrors."""
    proc = run(["adb", "-s", serial, "shell", "cmd", "display", "get-displays"])
    if proc is None or proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        if "DisplayInfo{" not in line or not re.search(r"\bdisplayId 0,", line):
            continue
        match = re.search(r"\breal (\d+) x (\d+)", line)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None


def scrcpy_pids(serial):
    """PIDs of scrcpy processes mirroring this serial."""
    pids = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open("/proc/%s/cmdline" % entry, "rb") as handle:
                argv = handle.read().split(b"\0")
        except OSError:
            continue
        if not argv or os.path.basename(argv[0]) != b"scrcpy":
            continue
        args = [arg.decode("utf-8", "replace") for arg in argv[1:]]
        if serial in args:
            pids.append(int(entry))
    return pids


def hyprctl_json(command):
    proc = run(["hyprctl", command, "-j"], timeout=8)
    if proc is None or proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def scrcpy_window(pids):
    clients = hyprctl_json("clients")
    if not isinstance(clients, list):
        return None
    for client in clients:
        if client.get("class") == "scrcpy" and client.get("pid") in pids:
            return client
    return None


def dispatch(expression):
    proc = run(["hyprctl", "dispatch", expression], timeout=8)
    return proc is not None and proc.returncode == 0 and "ok" in proc.stdout


def target_size(window, content):
    """Largest size with the content aspect that fits the monitor."""
    monitors = hyprctl_json("monitors")
    if not isinstance(monitors, list) or not monitors:
        return None
    index = window.get("monitor", 0)
    monitor = monitors[index] if 0 <= index < len(monitors) else monitors[0]
    scale = monitor.get("scale") or 1.0
    usable_width = int(monitor.get("width", 0) / scale) - DISPLAY_MARGIN
    usable_height = int(monitor.get("height", 0) / scale) - DISPLAY_MARGIN
    if usable_width <= 0 or usable_height <= 0:
        return None

    width, height = content
    factor = min(usable_width / width, usable_height / height)
    return max(1, int(width * factor)), max(1, int(height * factor))


def fits(content, size):
    """True when the window is already shaped like the video."""
    width, height = content
    win_width, win_height = size
    if win_width <= 0 or win_height <= 0:
        return False
    expected = width / height
    actual = win_width / win_height
    return abs(actual - expected) / expected <= ASPECT_TOLERANCE


def fit_window(window, content):
    size = target_size(window, content)
    if size is None:
        return False
    address = window.get("address", "")
    if not address:
        return False
    selector = 'window = "address:%s"' % address
    resized = dispatch("hl.dsp.window.resize({ x = %d, y = %d, %s })" % (size[0], size[1], selector))
    centered = dispatch("hl.dsp.window.center({ %s })" % selector)
    if resized and centered:
        log("phone %dx%d -> window %dx%d" % (content[0], content[1], size[0], size[1]))
        return True
    log("could not resize %s (resize=%s center=%s)" % (address, resized, centered))
    return False


def stop(signum, frame):
    global _stopping
    _stopping = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True, help="adb serial of the phone")
    parser.add_argument("--pid-file", help="write the watcher PID here")
    parser.add_argument(
        "--view",
        type=int,
        choices=(0, 90, 180, 270),
        default=0,
        help="scrcpy --display-orientation angle (the phone stays as it is)",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    if args.pid_file:
        try:
            with open(args.pid_file, "w") as handle:
                handle.write(str(os.getpid()) + "\n")
        except OSError:
            pass

    last_content = None
    last_monitor = None
    missing = 0
    try:
        while not _stopping:
            pids = scrcpy_pids(args.serial)
            if not pids:
                missing += 1
                if missing >= MISSING_LIMIT:
                    break
                time.sleep(POLL_INTERVAL)
                continue
            missing = 0

            content = display_size(args.serial)
            # --display-orientation turns the image, so at 90° and 270° the
            # video the window shows has the swapped aspect.
            if content and args.view in (90, 270):
                content = (content[1], content[0])
            window = scrcpy_window(pids)
            # A fullscreen window is controlled by the user; re-fit it only
            # after leaving fullscreen.
            if content and window and not window.get("fullscreen"):
                monitor = window.get("monitor", 0)
                if (content != last_content or monitor != last_monitor
                        or not fits(content, window.get("size", (0, 0)))):
                    if fit_window(window, content):
                        last_content = content
                        last_monitor = monitor
            time.sleep(POLL_INTERVAL)
    finally:
        if args.pid_file:
            try:
                with open(args.pid_file) as handle:
                    if handle.read().strip() == str(os.getpid()):
                        os.unlink(args.pid_file)
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
