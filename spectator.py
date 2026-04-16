"""
Auto-spectator for Dota 2's Watch tab.

Iterates through the live match list and enters games that haven't been
collected yet. Detection is pixel-based: if the "WATCH IN-GAME" button
is visible (bright pixel), the analytics panel has already been captured
for that match and it gets skipped.

Requires: pip install pyautogui
Must be run with Dota 2 open and visible on the primary monitor.
Press the mouse into any screen corner to trigger pyautogui's failsafe.
"""

import os
import time
import ctypes

import pyautogui

# ---------------------------------------------------------------------------
# Screen coordinates — calibrate these for your monitor resolution
# ---------------------------------------------------------------------------
WATCH_TAB = (850, 200)    # "Watch" tab button
REFRESH_BTN = (960, 570)  # first refresh click target
REFRESH_BTN2 = (960, 720) # second refresh click target
MATCH_LIST_X = 530        # X coordinate of the match list
MATCH_LIST_START_Y = 345  # Y of the first match entry
MATCH_ROW_STEP = 60       # pixels between match rows

CONSOLE_KEY = "f12"
DATA_COLLECT_SECONDS = 20  # how long to stay in each match

# ---------------------------------------------------------------------------
# Analytics panel detection
# Pixel at (CHECK_X, CHECK_Y) is bright when the panel is visible (skip match)
# and dark when it is not (enter match).
# ---------------------------------------------------------------------------
CHECK_PIXEL = (1040, 582)
PANEL_COLOR = (222, 229, 244)  # measured from the "WATCH IN-GAME" button
COLOR_TOLERANCE = 20


def _set_english_layout() -> None:
    """Switch keyboard layout to EN before typing console commands."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        ctypes.windll.user32.PostMessageA(hwnd, 0x0050, 0, 0x0409)
    except Exception:
        pass


def _panel_visible() -> bool:
    """Return True if the analytics panel is already shown for the selected match."""
    return pyautogui.pixelMatchesColor(
        *CHECK_PIXEL, PANEL_COLOR, tolerance=COLOR_TOLERANCE
    )


def spectate_match(index: int) -> None:
    """Click on match at position `index` and collect GSI data if not already done."""
    y = MATCH_LIST_START_Y + index * MATCH_ROW_STEP
    print(f"  Checking match slot {index + 1} (y={y})...")

    pyautogui.click(MATCH_LIST_X, y)
    time.sleep(5)

    if _panel_visible():
        print(f"  Slot {index + 1}: panel already present, skipping")
        return

    print(f"  Slot {index + 1}: entering match...")
    _set_english_layout()
    pyautogui.doubleClick(MATCH_LIST_X, y, interval=0.25)
    time.sleep(DATA_COLLECT_SECONDS)

    # Exit via console disconnect
    pyautogui.press("esc")
    time.sleep(0.5)
    pyautogui.press(CONSOLE_KEY)
    time.sleep(2.0)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.press("delete")
    pyautogui.write("disc", interval=0.20)
    pyautogui.press("enter")
    time.sleep(3.0)
    pyautogui.press(CONSOLE_KEY)

    print("  Waiting for menu to load (10s)...")
    time.sleep(10)


def refresh_match_list() -> None:
    """Reload the Watch tab match list."""
    pyautogui.click(*WATCH_TAB)
    time.sleep(2)
    pyautogui.click(*REFRESH_BTN)
    time.sleep(4)
    pyautogui.click(*REFRESH_BTN2)
    time.sleep(4)


def scroll_list() -> None:
    """Scroll the match list down to reveal additional entries."""
    print("Scrolling match list...")
    pyautogui.click(*WATCH_TAB)
    time.sleep(1.5)
    pyautogui.click(MATCH_LIST_X, MATCH_LIST_START_Y)
    time.sleep(0.5)
    pyautogui.scroll(-600)
    time.sleep(3.0)


def _dota_running() -> bool:
    return "dota2.exe" in os.popen('tasklist /FI "IMAGENAME eq dota2.exe"').read()


def main() -> None:
    pyautogui.FAILSAFE = True
    print("Dota 2 Auto-Spectator started. Move mouse to a corner to stop.")
    print(f"Detection pixel: {CHECK_PIXEL}, color: {PANEL_COLOR}, tolerance: {COLOR_TOLERANCE}")
    time.sleep(5)

    cycle = 0
    while True:
        if not _dota_running():
            print("Dota 2 not running, waiting 20s...")
            time.sleep(20)
            continue

        cycle += 1
        print(f"\n=== Cycle {cycle} ===")
        refresh_match_list()

        for i in range(8):
            spectate_match(i)

        scroll_list()

        for i in range(5):
            spectate_match(i)


if __name__ == "__main__":
    main()
