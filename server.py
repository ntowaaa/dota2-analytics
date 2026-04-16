"""
GSI receiver server for Dota 2.

Listens for Game State Integration payloads on port 3000,
enriches player data with leaderboard ranks, saves matches to CSV
when the match ID changes, and broadcasts updates via Socket.IO.
"""

import csv
import json
import os
from datetime import datetime

from flask import Flask, request
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

CSV_FILE = "dota_matches_history.csv"
LEADERBOARD_FILE = "processed_leaderboard.csv"

# GSI state
current_match_id: str | None = None
last_saved_data: dict | None = None

# Leaderboard: {player_name: {rank, team}}
leaderboard: dict[str, dict] = {}


def _load_leaderboard() -> dict[str, dict]:
    if not os.path.exists(LEADERBOARD_FILE):
        return {}
    result = {}
    with open(LEADERBOARD_FILE, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            nick = row.get("Никнейм")
            if nick:
                result[nick] = {
                    "rank": row.get("Место в ладдере", ""),
                    "team": row.get("Команда", ""),
                }
    print(f"Leaderboard loaded: {len(result)} entries")
    return result


leaderboard = _load_leaderboard()


def format_clock(seconds: int | float) -> str:
    if not isinstance(seconds, (int, float)):
        return "00:00"
    sign = "-" if seconds < 0 else ""
    total = int(abs(seconds))
    return f"{sign}{total // 60:02}:{total % 60:02}"


def _parse_items(slot_data: dict) -> str:
    """Build a comma-separated item string from a player's item slot dict."""
    items = []
    for i in range(6):
        name = slot_data.get(f"slot{i}", {}).get("name", "empty")
        if name != "empty":
            items.append(name.replace("item_", ""))
    neutral = slot_data.get("neutral0", {}).get("name", "empty")
    if neutral != "empty":
        items.append(f"[{neutral.replace('item_', '')}]")
    return ", ".join(items)


def _extract_players(
    team_players: dict,
    team_heroes: dict,
    team_items: dict,
) -> list[dict]:
    """Parse raw GSI dicts into a sorted list of player records."""
    players = []
    for slot, p in team_players.items():
        h = team_heroes.get(slot, {})
        lb = leaderboard.get(p.get("name", ""), {})
        players.append({
            "name": p.get("name", "Unknown"),
            "accountid": p.get("accountid") or p.get("steamid", ""),
            "hero": h.get("name", "").replace("npc_dota_hero_", ""),
            "facet": h.get("facet", 0),
            "net_worth": p.get("net_worth", 0),
            "level": h.get("level", 0),
            "kills": p.get("kills", 0),
            "deaths": p.get("deaths", 0),
            "assists": p.get("assists", 0),
            "lb_rank": lb.get("rank", ""),
            "lb_team": lb.get("team", ""),
            "items_str": _parse_items(team_items.get(slot, {})),
        })
    # Assign roles by descending net worth (rough approximation)
    players.sort(key=lambda p: p["net_worth"], reverse=True)
    for i, p in enumerate(players):
        p["role"] = i + 1
    return players


def _save_match(data: dict) -> None:
    """Write a match snapshot to the CSV file, replacing any prior entry for that match."""
    match_id = str(data["match_id"])
    game_time = data.get("clock_time_formatted", "00:00")
    nw_lead = data["lead"]
    lead_label = (
        f"Radiant +{nw_lead}" if nw_lead >= 0 else f"Dire +{abs(nw_lead)}"
    )

    headers = [
        "Date", "Match ID", "Game Time", "Team", "Role", "Hero", "Facet",
        "Player Name", "LB Rank", "LB Team", "AccountID", "Net Worth",
        "Level", "K/D/A", "Total Team Kills", "NW Lead", "Radiant Win Chance %",
        "Items",
    ]

    existing_rows: list[dict] = []
    if os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, encoding="utf-8-sig") as f:
                content = f.read()
                if content.startswith("sep="):
                    content = content.split("\n", 1)[1]
                for row in csv.DictReader(content.splitlines()):
                    if row.get("Match ID") != match_id:
                        existing_rows.append(row)
        except Exception as e:
            print(f"Warning: could not read existing CSV: {e}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_rows = []
    for team_key in ("radiant", "dire"):
        team_kills = data[f"{team_key}_kills"]
        for p in data[team_key]:
            new_rows.append({
                "Date": now,
                "Match ID": match_id,
                "Game Time": game_time,
                "Team": team_key.capitalize(),
                "Role": p["role"],
                "Hero": p["hero"],
                "Facet": p["facet"],
                "Player Name": p["name"],
                "LB Rank": p["lb_rank"],
                "LB Team": p["lb_team"],
                "AccountID": p["accountid"],
                "Net Worth": p["net_worth"],
                "Level": p["level"],
                "K/D/A": f"{p['kills']}/{p['deaths']}/{p['assists']}",
                "Total Team Kills": team_kills,
                "NW Lead": lead_label,
                "Radiant Win Chance %": data["win_chance"],
                "Items": p["items_str"],
            })

    try:
        with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
            f.write("sep=,\n")
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(existing_rows)
            writer.writerows(new_rows)
        print(f"Saved match {match_id} to CSV")
    except PermissionError:
        print("ERROR: CSV file is open in another program. Close it and try again.")


@app.route("/dota", methods=["POST"])
def receive_gsi():
    global current_match_id, last_saved_data

    data = request.json
    if not data:
        return "No data", 400

    map_data = data.get("map", {})
    new_match_id = map_data.get("matchid")
    clock_fmt = format_clock(map_data.get("clock_time", 0))

    # Flush previous match when a new one starts
    if new_match_id and str(new_match_id) != str(current_match_id):
        if last_saved_data and str(last_saved_data["match_id"]) != "0":
            _save_match(last_saved_data)
        current_match_id = new_match_id

    all_players = data.get("player", {})
    all_heroes = data.get("hero", {})
    all_items = data.get("items", {})

    state = {
        "match_id": new_match_id or "0",
        "lead": 0,
        "win_chance": map_data.get("radiant_win_chance", "N/A"),
        "radiant_kills": map_data.get("radiant_score", 0),
        "dire_kills": map_data.get("dire_score", 0),
        "clock_time_formatted": clock_fmt,
        "radiant": _extract_players(
            all_players.get("team2", {}),
            all_heroes.get("team2", {}),
            all_items.get("team2", {}),
        ),
        "dire": _extract_players(
            all_players.get("team3", {}),
            all_heroes.get("team3", {}),
            all_items.get("team3", {}),
        ),
    }

    rad_nw = sum(p["net_worth"] for p in state["radiant"])
    dire_nw = sum(p["net_worth"] for p in state["dire"])
    state["lead"] = rad_nw - dire_nw

    if new_match_id:
        last_saved_data = state

    socketio.emit("dota_update", state)
    return "OK", 200


@app.route("/")
def index():
    from flask import render_template
    return render_template("index.html")


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=3000)
