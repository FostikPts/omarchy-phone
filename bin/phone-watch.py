#!/usr/bin/env python3
"""Keep the scrcpy window useful without fighting the user.

Wayland gives a client no way to resize or move its own toplevel window, and
Hyprland has no per-window rotation. So when the phone display rotates (or its
size changes), scrcpy's video changes aspect ratio but its window keeps the old
shape. This watcher polls the mirrored display and asks Hyprland (through
hyprctl) for a new size, keeping the window where the user put it.

Rules:

* A manual resize or move is never undone. The watcher only changes the window
  when the phone display itself changes (rotation, resolution) or on the very
  first start when there is no saved geometry yet.
* The window is resized around its current centre, so it does not jump back to
  the middle of the screen.
* The window's long side is kept across a rotation: a small window stays
  small, it only gets the new aspect ratio.
* The last geometry is saved to disk and restored on the next mirror run.

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

DISPLAY_MARGIN = 96  # scrcpy leaves this much room around its initial window
POLL_INTERVAL = 1.0
ASPECT_TOLERANCE = 0.02
GEOMETRY_TOLERANCE = 4  # px; smaller differences are rounding, not the user
MANUAL_CONFIRM_POLLS = 2  # save a manual change after it stays put this long
MIN_WINDOW_SIZE = 120
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


def window_geometry(window):
    """(x, y, width, height) of a Hyprland client in layout coordinates."""
    at = window.get("at") or [0, 0]
    size = window.get("size") or [0, 0]
    try:
        return int(at[0]), int(at[1]), int(size[0]), int(size[1])
    except (TypeError, ValueError, IndexError):
        return 0, 0, 0, 0


def monitor_bounds(monitors, window):
    """Usable layout rectangle of the monitor the window sits on."""
    if not isinstance(monitors, list) or not monitors:
        return None
    index = window.get("monitor", 0)
    monitor = monitors[index] if 0 <= index < len(monitors) else monitors[0]
    scale = monitor.get("scale") or 1.0
    width = int(monitor.get("width", 0) / scale)
    height = int(monitor.get("height", 0) / scale)
    if int(monitor.get("transform", 0) or 0) % 2 == 1:
        width, height = height, width

    reserved = monitor.get("reserved") or [0, 0, 0, 0]
    if isinstance(reserved, dict):
        left = int(reserved.get("left", 0))
        top = int(reserved.get("top", 0))
        right = int(reserved.get("right", 0))
        bottom = int(reserved.get("bottom", 0))
    else:
        values = list(reserved) + [0, 0, 0, 0]
        left, top, right, bottom = (int(values[i]) for i in range(4))

    x = int(monitor.get("x", 0)) + left
    y = int(monitor.get("y", 0)) + top
    width -= left + right
    height -= top + bottom
    if width <= 0 or height <= 0:
        return None
    return {
        "name": monitor.get("name", ""),
        "x": x,
        "y": y,
        "w": width,
        "h": height,
    }


def clamp_size(width, height, bounds):
    width = max(MIN_WINDOW_SIZE, min(int(width), bounds["w"]))
    height = max(MIN_WINDOW_SIZE, min(int(height), bounds["h"]))
    return width, height


def fit_size(width, height, bounds):
    """Shrink a size to the monitor without changing its aspect ratio."""
    width = max(1.0, float(width))
    height = max(1.0, float(height))
    factor = min(1.0, bounds["w"] / width, bounds["h"] / height)
    return clamp_size(round(width * factor), round(height * factor), bounds)


def clamp_position(x, y, width, height, bounds):
    max_x = bounds["x"] + bounds["w"] - width
    max_y = bounds["y"] + bounds["h"] - height
    x = max(bounds["x"], min(int(x), max_x))
    y = max(bounds["y"], min(int(y), max_y))
    return x, y


def centered(x, y, width, height, bounds):
    """A size centred on (x, y), clamped so it stays on screen."""
    left = int(round(x - width / 2.0))
    top = int(round(y - height / 2.0))
    return clamp_position(left, top, width, height, bounds)


def target_size(content, bounds, margin=0):
    """Largest size with the content aspect that fits the monitor."""
    usable_width = bounds["w"] - margin * 2
    usable_height = bounds["h"] - margin * 2
    if usable_width <= 0 or usable_height <= 0:
        return None
    width, height = content
    factor = min(usable_width / width, usable_height / height)
    return clamp_size(width * factor, height * factor, bounds)


def size_for_rotation(content, geometry, bounds):
    """New aspect ratio with the window's long side kept the same size.

    This keeps a window the user made small small, and a maximised one
    maximised, without letterboxed windows shrinking to a tiny strip.
    """
    long_side = max(geometry[2], geometry[3])
    content_width, content_height = content
    if content_width >= content_height:
        width = long_side
        height = long_side * content_height / content_width
    else:
        width = long_side * content_width / content_height
        height = long_side
    return fit_size(width, height, bounds)


def fits_content(aspect_a, aspect_b):
    if aspect_a <= 0 or aspect_b <= 0:
        return False
    return abs(aspect_a - aspect_b) / aspect_b <= ASPECT_TOLERANCE


def read_geometry(path):
    try:
        with open(path) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        geometry = {
            "x": int(data["x"]),
            "y": int(data["y"]),
            "w": int(data["w"]),
            "h": int(data["h"]),
            "content_w": int(data.get("content_w", 0)),
            "content_h": int(data.get("content_h", 0)),
            "monitor": str(data.get("monitor", "")),
        }
    except (KeyError, TypeError, ValueError):
        return None
    if geometry["w"] <= 0 or geometry["h"] <= 0:
        return None
    return geometry


def write_geometry(path, geometry, content, bounds):
    payload = {
        "x": geometry[0],
        "y": geometry[1],
        "w": geometry[2],
        "h": geometry[3],
        "content_w": content[0] if content else 0,
        "content_h": content[1] if content else 0,
        "monitor": bounds["name"] if bounds else "",
    }
    directory = os.path.dirname(path)
    if directory:
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError:
            return
    temporary = path + ".tmp"
    try:
        with open(temporary, "w") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass


def apply_geometry(window, geometry):
    address = window.get("address", "")
    if not address:
        return False
    selector = 'window = "address:%s"' % address
    x, y, width, height = geometry
    resized = dispatch(
        "hl.dsp.window.resize({ x = %d, y = %d, relative = false, %s })"
        % (width, height, selector)
    )
    moved = dispatch(
        "hl.dsp.window.move({ x = %d, y = %d, relative = false, %s })"
        % (x, y, selector)
    )
    if resized and moved:
        return True
    log(
        "could not place %s (resize=%s move=%s)"
        % (address, resized, moved)
    )
    return resized or moved


def restored_geometry(saved, content, bounds):
    """Saved size adapted to the current phone content and monitor."""
    width, height = int(saved["w"]), int(saved["h"])
    saved_content = (saved.get("content_w", 0), saved.get("content_h", 0))
    if saved_content[0] > 0 and saved_content[1] > 0:
        if fits_content(
            saved_content[0] / saved_content[1], content[0] / content[1]
        ):
            width, height = fit_size(width, height, bounds)
        else:
            width, height = size_for_rotation(
                content, (0, 0, width, height), bounds
            )
    else:
        width, height = fit_size(width, height, bounds)

    centre_x = saved["x"] + saved["w"] / 2.0
    centre_y = saved["y"] + saved["h"] / 2.0
    x, y = centered(centre_x, centre_y, width, height, bounds)
    return x, y, width, height


def oriented_content(serial, view):
    content = display_size(serial)
    if content and view in (90, 270):
        content = (content[1], content[0])
    return content


def stop(signum, frame):
    global _stopping
    _stopping = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True, help="adb serial of the phone")
    parser.add_argument("--pid-file", help="write the watcher PID here")
    parser.add_argument(
        "--geometry",
        default=os.path.expanduser("~/.local/state/omarchy-phone/geometry.json"),
        help="where the last window geometry is remembered",
    )
    parser.add_argument(
        "--fit",
        choices=("rotate", "never"),
        default="rotate",
        help="refit on phone rotation/resolution change, or never touch the window",
    )
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
    last_applied = None
    restored = False
    manual_candidate = None
    manual_count = 0
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

            window = scrcpy_window(pids)
            # A fullscreen window is controlled by the user; fit it again only
            # after leaving fullscreen.
            if not window or window.get("fullscreen"):
                time.sleep(POLL_INTERVAL)
                continue

            # --display-orientation turns the image, so at 90° and 270° the
            # video the window shows has the swapped aspect.
            content = oriented_content(args.serial, args.view)
            if not content:
                time.sleep(POLL_INTERVAL)
                continue

            monitors = hyprctl_json("monitors")
            bounds = monitor_bounds(monitors, window)
            if not bounds:
                time.sleep(POLL_INTERVAL)
                continue

            geometry = window_geometry(window)
            if geometry[2] <= 0 or geometry[3] <= 0:
                time.sleep(POLL_INTERVAL)
                continue

            if not restored:
                saved = read_geometry(args.geometry)
                if saved is not None:
                    wanted = restored_geometry(saved, content, bounds)
                    if apply_geometry(window, wanted):
                        restored = True
                        last_applied = wanted
                        last_content = content
                        log(
                            "restored %dx%d at %d,%d"
                            % (wanted[2], wanted[3], wanted[0], wanted[1])
                        )
                        time.sleep(POLL_INTERVAL)
                        continue

                if args.fit == "never":
                    restored = True
                    last_content = content
                    log("no saved geometry; leaving the window as it is")
                    time.sleep(POLL_INTERVAL)
                    continue

                size = target_size(content, bounds, DISPLAY_MARGIN)
                if size is not None:
                    centre_x = bounds["x"] + bounds["w"] / 2.0
                    centre_y = bounds["y"] + bounds["h"] / 2.0
                    x, y = centered(centre_x, centre_y, size[0], size[1], bounds)
                    wanted = (x, y, size[0], size[1])
                    if apply_geometry(window, wanted):
                        restored = True
                        write_geometry(args.geometry, wanted, content, bounds)
                        last_applied = wanted
                        last_content = content
                        log(
                            "initial %dx%d at %d,%d"
                            % (wanted[2], wanted[3], wanted[0], wanted[1])
                        )
                        time.sleep(POLL_INTERVAL)
                        continue
                # hyprctl did not answer yet; try again on the next poll.
                time.sleep(POLL_INTERVAL)
                continue

            if last_content is not None and content != last_content:
                if args.fit == "rotate":
                    size = size_for_rotation(content, geometry, bounds)
                    if size is not None:
                        centre_x = geometry[0] + geometry[2] / 2.0
                        centre_y = geometry[1] + geometry[3] / 2.0
                        x, y = centered(
                            centre_x, centre_y, size[0], size[1], bounds
                        )
                        wanted = (x, y, size[0], size[1])
                        if apply_geometry(window, wanted):
                            write_geometry(args.geometry, wanted, content, bounds)
                            last_applied = wanted
                            last_content = content
                            log(
                                "phone %dx%d -> window %dx%d at %d,%d"
                                % (
                                    content[0],
                                    content[1],
                                    wanted[2],
                                    wanted[3],
                                    wanted[0],
                                    wanted[1],
                                )
                            )
                else:
                    last_content = content
                manual_candidate = None
                manual_count = 0
                time.sleep(POLL_INTERVAL)
                continue

            # Remember a resize/move the user made by hand, but only once it
            # settles, so dragging does not write the file on every poll.
            if last_applied is not None:
                delta = max(
                    abs(geometry[i] - last_applied[i]) for i in range(4)
                )
                if delta > GEOMETRY_TOLERANCE:
                    if (
                        manual_candidate is not None
                        and max(
                            abs(geometry[i] - manual_candidate[i])
                            for i in range(4)
                        )
                        <= GEOMETRY_TOLERANCE
                    ):
                        manual_count += 1
                    else:
                        manual_candidate = geometry
                        manual_count = 1
                    if manual_count >= MANUAL_CONFIRM_POLLS:
                        write_geometry(args.geometry, geometry, content, bounds)
                        last_applied = geometry
                        manual_candidate = None
                        manual_count = 0
                        log(
                            "saved manual %dx%d at %d,%d"
                            % (geometry[2], geometry[3], geometry[0], geometry[1])
                        )
                else:
                    manual_candidate = None
                    manual_count = 0

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
