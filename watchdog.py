"""
Watchdog for Dota 2: restarts the game if it hangs or closes,
and performs a scheduled hourly reboot to prevent memory leaks / slowdowns.

Requires: pip install psutil pyautogui
"""

import ctypes
import os
import time

import psutil
import pyautogui

DOTA_PROCESS = "dota2.exe"
DOTA_WINDOW  = "Dota 2"
DOTA_STEAM_URL = "steam://rungameid/570"
WATCH_TAB = (850, 200)

REBOOT_INTERVAL = 3600   # seconds
CHECK_INTERVAL  = 15     # seconds between health checks
STATUS_INTERVAL = 300    # print time-to-reboot every N seconds

_user32 = ctypes.windll.user32


def _is_responding() -> bool:
    """Return False if the Dota 2 window exists but is hung, True otherwise."""
    hwnd = _user32.FindWindowW(None, DOTA_WINDOW)
    if not hwnd:
        # Window not found — check if the process at least exists
        return any(p.info["name"] == DOTA_PROCESS for p in psutil.process_iter(["name"]))
    return not _user32.IsHungAppWindow(hwnd)


def restart(reason: str = "unresponsive or closed") -> None:
    print(f"[{time.strftime('%H:%M:%S')}] Restarting Dota 2: {reason}")
    os.system(f"taskkill /f /im {DOTA_PROCESS} >nul 2>&1")
    time.sleep(5)
    os.startfile(DOTA_STEAM_URL)
    print("Waiting 60s for game to load...")
    time.sleep(60)
    try:
        pyautogui.click(*WATCH_TAB)
    except Exception as e:
        print(f"Could not click Watch tab: {e}")


def main() -> None:
    print(f"Watchdog started. Reboot interval: {REBOOT_INTERVAL // 60} min.")
    last_reboot = time.time()

    while True:
        now = time.time()
        elapsed = now - last_reboot

        if not _is_responding():
            restart("unresponsive or closed")
            last_reboot = time.time()
        elif elapsed > REBOOT_INTERVAL:
            restart("scheduled hourly reboot")
            last_reboot = time.time()
        else:
            remaining = int(REBOOT_INTERVAL - elapsed)
            if remaining % STATUS_INTERVAL == 0:
                print(f"Next reboot in {remaining // 60} min")
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
