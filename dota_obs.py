"""
Personal match tracker with OBS integration.

Receives GSI data on port 3000, records win/loss outcomes, tracks per-session
and historical stats, and writes text files that OBS reads as text sources.
Also switches OBS scenes automatically during hero selection (anti-sniping).

Requires: pip install obs-websocket-py
"""

import http.server
import json
import os
from collections import defaultdict
from datetime import datetime

from obswebsocket import obsws, requests as obs_requests

OBS_HOST     = "127.0.0.1"
OBS_PORT     = 4455
OBS_PASSWORD = "your_obs_password_here"   # set in OBS WebSocket settings

SCENE_GAME = "Dota Game Scene"
SCENE_PICK = "Anti-Sniping Scene"

STATS_FILE    = "match_history.json"
MMR_FILE      = "current_mmr.txt"
MMR_SAVE_FILE = "current_mmr_value.json"
STREAK_FILE   = "streak.txt"
WINRATE_FILE  = "winrate.txt"
HERO_FILE     = "hero_stats.txt"
ITEM_FILE     = "item_stats.txt"
SESSION_FILE  = "session_stats.txt"

DEFAULT_MMR = 0   # set your starting MMR here

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_current_state: str | None = None
_session_wins   = 0
_session_losses = 0

match_history: list[dict] = []
if os.path.exists(STATS_FILE):
    with open(STATS_FILE, encoding="utf-8") as f:
        match_history = json.load(f)

if os.path.exists(MMR_SAVE_FILE):
    with open(MMR_SAVE_FILE, encoding="utf-8") as f:
        current_mmr: float = json.load(f).get("mmr", DEFAULT_MMR)
else:
    current_mmr = DEFAULT_MMR


# ---------------------------------------------------------------------------
# OBS helpers
# ---------------------------------------------------------------------------

def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def switch_scene(scene: str) -> None:
    ws = obsws(OBS_HOST, OBS_PORT, OBS_PASSWORD)
    try:
        ws.connect()
        ws.call(obs_requests.SetCurrentProgramScene(sceneName=scene))
        ws.disconnect()
        print(f"[OBS] Switched to: {scene}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Stats file writers
# ---------------------------------------------------------------------------

def write_mmr(mmr: float) -> None:
    _write(MMR_FILE, f"MMR: {int(mmr)}")
    with open(MMR_SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump({"mmr": mmr}, f)


def write_streak(history: list[dict]) -> None:
    if not history:
        _write(STREAK_FILE, "")
        return
    last_result = history[-1]["result"]
    streak = sum(1 for _ in (
        m for m in reversed(history) if m["result"] == last_result
    ) if True)
    # simpler: count from the end
    streak = 0
    for m in reversed(history):
        if m["result"] == last_result:
            streak += 1
        else:
            break
    label = "W" if last_result == "WIN" else "L"
    _write(STREAK_FILE, f"{label}{streak}")


def write_winrate(history: list[dict]) -> None:
    if not history:
        _write(WINRATE_FILE, "WR: -")
        return
    wins = sum(1 for m in history if m["result"] == "WIN")
    wr = round(wins / len(history) * 100)
    _write(WINRATE_FILE, f"WR: {wr}% ({wins}/{len(history)})")


def write_hero_stats(history: list[dict]) -> None:
    heroes: dict[str, dict] = defaultdict(lambda: {"wins": 0, "total": 0})
    for m in history:
        hero = m.get("hero", "unknown").replace("npc_dota_hero_", "")
        heroes[hero]["total"] += 1
        if m["result"] == "WIN":
            heroes[hero]["wins"] += 1

    lines = []
    for hero, stat in sorted(heroes.items(), key=lambda x: -x[1]["total"]):
        wr = round(stat["wins"] / stat["total"] * 100)
        lines.append(f"{hero}: {wr}% ({stat['total']} games)")
    _write(HERO_FILE, "\n".join(lines) or "-")


def write_item_stats(history: list[dict]) -> None:
    wins:   dict[str, int] = defaultdict(int)
    losses: dict[str, int] = defaultdict(int)
    for m in history:
        for item in m.get("inventory", []):
            key = item.replace("item_", "")
            if m["result"] == "WIN":
                wins[key] += 1
            else:
                losses[key] += 1

    stats = []
    for item in set(wins) | set(losses):
        total = wins[item] + losses[item]
        if total < 2:
            continue
        wr = round(wins[item] / total * 100)
        stats.append((item, wr, total))

    if not stats:
        _write(ITEM_FILE, "- not enough data -")
        return

    best  = sorted(stats, key=lambda x: -x[1])
    worst = sorted(stats, key=lambda x: x[1])
    lines = ["+ Best items:"] + [f"  {i}: {w}% ({t})" for i, w, t in best]
    lines += ["- Worst items:"] + [f"  {i}: {w}% ({t})" for i, w, t in worst]
    _write(ITEM_FILE, "\n".join(lines))


def write_session() -> None:
    total = _session_wins + _session_losses
    delta = (_session_wins - _session_losses) * 25
    sign  = "+" if delta >= 0 else ""
    _write(SESSION_FILE, f"Session: {_session_wins}W / {_session_losses}L  |  {sign}{delta} MMR")


def _get_inventory(data: dict) -> list[str]:
    items_block = data.get("items", {})
    return [
        items_block[f"slot{i}"]["name"]
        for i in range(16)
        if f"slot{i}" in items_block and items_block[f"slot{i}"].get("name", "empty") != "empty"
    ]


def _time_of_day(hour: int) -> str:
    if 6  <= hour < 12: return "morning"
    if 12 <= hour < 18: return "afternoon"
    if 18 <= hour < 24: return "evening"
    return "night"


# ---------------------------------------------------------------------------
# Match recording
# ---------------------------------------------------------------------------

def record_match(data: dict, winner_side: str) -> None:
    global current_mmr, _session_wins, _session_losses

    match_id = data.get("map", {}).get("matchid", "unknown")
    if any(m["id"] == match_id for m in match_history):
        return

    my_side = data.get("player", {}).get("team_name")
    won = my_side == winner_side

    mmr_change = 24.1 if won else -24.87
    current_mmr += mmr_change
    write_mmr(current_mmr)

    now = datetime.now()
    entry = {
        "id": match_id,
        "hero": data.get("hero", {}).get("name", "unknown"),
        "inventory": _get_inventory(data),
        "result": "WIN" if won else "LOSS",
        "mmr_change": mmr_change,
        "new_mmr": current_mmr,
        "timestamp": now.isoformat(),
        "time_of_day": _time_of_day(now.hour),
    }

    if won:
        _session_wins += 1
    else:
        _session_losses += 1

    match_history.append(entry)
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(match_history, f, indent=2, ensure_ascii=False)

    write_streak(match_history)
    write_winrate(match_history)
    write_hero_stats(match_history)
    write_item_stats(match_history)
    write_session()

    sign = "+" if mmr_change > 0 else ""
    print(f"[Match] {'WIN' if won else 'LOSS'} | MMR: {int(current_mmr)} ({sign}{mmr_change})")
    print(f"        Hero: {entry['hero'].replace('npc_dota_hero_', '')} | {entry['time_of_day']}")
    print(f"        Session: {_session_wins}W / {_session_losses}L")


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class GsiHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        global _current_state
        length = int(self.headers["Content-Length"])
        data = json.loads(self.rfile.read(length).decode())

        map_data = data.get("map", {})
        new_state = map_data.get("game_state")
        winner    = map_data.get("win_team")

        if new_state and new_state != _current_state:
            if new_state == "DOTA_GAMERULES_STATE_HERO_SELECTION":
                switch_scene(SCENE_PICK)
            elif new_state == "DOTA_GAMERULES_STATE_STRATEGY_TIME":
                switch_scene(SCENE_GAME)
            _current_state = new_state

        if winner and winner != "none":
            record_match(data, winner)

        self.send_response(200)
        self.end_headers()

    def log_message(self, *_) -> None:
        pass  # suppress default access log


if __name__ == "__main__":
    write_mmr(current_mmr)
    write_streak(match_history)
    write_winrate(match_history)
    write_hero_stats(match_history)
    write_item_stats(match_history)
    write_session()

    print(f"GSI server started on :3000  |  MMR: {int(current_mmr)}  |  History: {len(match_history)} matches")
    http.server.HTTPServer(("localhost", 3000), GsiHandler).serve_forever()
