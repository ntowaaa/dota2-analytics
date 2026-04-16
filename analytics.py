"""
Match analytics: reads dota_matches_history_w_rank.csv,
filters by game duration and average leaderboard rank,
and outputs hero_stats.csv and player_stats.csv.
"""

import os
import traceback
from typing import Optional

import pandas as pd

INPUT_FILE = "dota_matches_history_w_rank.csv"
MIN_GAME_MINUTES = 15
RANK_THRESHOLD = 1500

# Internal hero ID -> display name. Covers most Dota 2 heroes;
# anything not listed falls back to title-cased ID.
HERO_NAMES: dict[str, str] = {
    "invoker": "Invoker", "treant": "Treant Protector", "razor": "Razor",
    "winter_wyvern": "Winter Wyvern", "enigma": "Enigma", "clinkz": "Clinkz",
    "omniknight": "Omniknight", "visage": "Visage", "broodmother": "Broodmother",
    "dazzle": "Dazzle", "lich": "Lich", "slark": "Slark",
    "shadow_shaman": "Shadow Shaman", "pudge": "Pudge", "nyx_assassin": "Nyx Assassin",
    "bounty_hunter": "Bounty Hunter", "elder_titan": "Elder Titan",
    "spirit_breaker": "Spirit Breaker", "venomancer": "Venomancer",
    "phantom_lancer": "Phantom Lancer", "nevermore": "Shadow Fiend",
    "lion": "Lion", "drow_ranger": "Drow Ranger", "undying": "Undying",
    "arc_warden": "Arc Warden", "legion_commander": "Legion Commander",
    "huskar": "Huskar", "earth_spirit": "Earth Spirit", "magnataur": "Magnus",
    "shredder": "Timbersaw", "life_stealer": "Lifestealer",
    "windrunner": "Windranger", "zuus": "Zeus", "furion": "Nature's Prophet",
    "abaddon": "Abaddon", "bane": "Bane", "beastmaster": "Beastmaster",
    "chen": "Chen", "clockwerk": "Clockwerk", "doom_bringer": "Doom",
    "ember_spirit": "Ember Spirit", "faceless_void": "Faceless Void",
    "gyrocopter": "Gyrocopter", "jakiro": "Jakiro", "juggernaut": "Juggernaut",
    "kunkka": "Kunkka", "leshrac": "Leshrac", "lina": "Lina",
    "lone_druid": "Lone Druid", "luna": "Luna", "meepo": "Meepo",
    "morphling": "Morphling", "naga_siren": "Naga Siren",
    "necrolyte": "Necrophos", "night_stalker": "Night Stalker",
    "ogre_magi": "Ogre Magi", "oracle": "Oracle",
    "outworld_destroyer": "Outworld Destroyer", "pangolier": "Pangolier",
    "phantom_assassin": "Phantom Assassin", "phoenix": "Phoenix",
    "puck": "Puck", "pugna": "Pugna", "queenofpain": "Queen of Pain",
    "riki": "Riki", "rubick": "Rubick", "sand_king": "Sand King",
    "shadow_demon": "Shadow Demon", "skywrath_mage": "Skywrath Mage",
    "sniper": "Sniper", "spectre": "Spectre", "storm_spirit": "Storm Spirit",
    "sven": "Sven", "techies": "Techies", "templar_assassin": "Templar Assassin",
    "tidehunter": "Tidehunter", "tinker": "Tinker", "tiny": "Tiny",
    "tusk": "Tusk", "ursa": "Ursa", "vengefulspirit": "Vengeful Spirit",
    "viper": "Viper", "weaver": "Weaver", "witch_doctor": "Witch Doctor",
    "wraith_king": "Wraith King",
}


def _hero_display(hero_id: str) -> str:
    return HERO_NAMES.get(str(hero_id).lower(), str(hero_id).capitalize())


def _game_minutes(time_str: str) -> int:
    """Parse 'MM:SS' and return the minute component."""
    try:
        parts = str(time_str).strip().split(":")
        return int(parts[0]) if len(parts) == 2 else 0
    except (ValueError, IndexError):
        return 0


def _is_win(row: pd.Series) -> int:
    """Return 1 if the player's team won, based on Radiant Win Chance."""
    team = str(row["Team"]).strip().capitalize()
    try:
        chance = float(row["Radiant Win Chance %"])
    except (ValueError, TypeError):
        return 0
    if team == "Radiant":
        return 1 if chance > 50 else 0
    if team == "Dire":
        return 1 if chance < 50 else 0
    return 0


def _kda(kda_str: str) -> float:
    try:
        k, d, a = map(int, str(kda_str).split("/"))
        return (k + a) / max(1, d)
    except (ValueError, AttributeError):
        return 0.0


def _pos_summary(group: pd.DataFrame, pos: int) -> str:
    sub = group[group["Role"] == pos]
    if sub.empty:
        return "0 (0%)"
    wr = sub["is_win"].mean()
    return f"{len(sub)} ({wr:.0%})"


def build_hero_stats(df: pd.DataFrame) -> pd.DataFrame:
    records = []
    for hero_id, grp in df.groupby("Hero"):
        name = _hero_display(hero_id)
        pos_cols = {f"Поз {p}": _pos_summary(grp, p) for p in range(1, 6)}
        facets = " | ".join(
            f"Ф{int(f)}: {len(g)} ({g['is_win'].mean():.0%})"
            for f, g in grp.groupby("Facet")
            if pd.notna(f)
        )
        top_players = ", ".join(
            grp[grp["is_win"] == 1]["Player Name"]
            .value_counts()
            .head(3)
            .index
            .tolist()
        )
        records.append({
            "Герой": name,
            "Игры": len(grp),
            "WR": f"{grp['is_win'].mean():.0%}",
            **pos_cols,
            "KDA": round(grp["kda_ratio"].mean(), 2),
            "NW": int(grp["Net Worth"].mean() or 0),
            "Фасеты": facets,
            "Топ игроки": top_players,
        })
    col_order = ["Герой", "Игры", "WR", "Поз 1", "Поз 2", "Поз 3", "Поз 4", "Поз 5",
                 "KDA", "NW", "Фасеты", "Топ игроки"]
    return pd.DataFrame(records).reindex(columns=col_order)


def build_player_stats(df: pd.DataFrame) -> pd.DataFrame:
    records = []
    for account_id, grp in df.groupby("AccountID"):
        last = grp.iloc[-1]
        hero_counts = grp.groupby("Hero").size().sort_values(ascending=False)
        hero_usage = [
            f"{_hero_display(h)}: {count} ({grp[grp['Hero'] == h]['is_win'].mean():.0%})"
            for h, count in hero_counts.items()
        ]
        records.append({
            "Никнейм": last["Player Name"],
            "Rank": last["LB Rank"],
            "Team": last["LB Team"],
            "Игры": len(grp),
            "WR": f"{grp['is_win'].mean():.0%}",
            "KDA": round(grp["kda_ratio"].mean(), 2),
            "NW": int(grp["Net Worth"].mean() or 0),
            "Герои (по убыванию)": " | ".join(hero_usage),
            "AccountID": f"\t{str(account_id).replace(chr(9), '')}",
        })
    return pd.DataFrame(records)


def run() -> None:
    if not os.path.exists(INPUT_FILE):
        print(f"File not found: {INPUT_FILE}")
        return

    try:
        df = pd.read_csv(INPUT_FILE, sep=";", skiprows=1, encoding="utf-8-sig")
        df.columns = df.columns.str.strip()

        df["LB Rank"] = df["LB Rank"].astype(str).str.replace("\t", "").str.strip()
        df["rank_numeric"] = pd.to_numeric(df["LB Rank"], errors="coerce")
        df["minutes"] = df["Game Time"].apply(_game_minutes)

        before = df["Match ID"].nunique()
        df = df[df["minutes"] > MIN_GAME_MINUTES].copy()
        after_time = df["Match ID"].nunique()
        print(f"Duration filter (>{MIN_GAME_MINUTES} min): {before} -> {after_time} matches")

        match_avg_rank = df.groupby("Match ID")["rank_numeric"].mean()
        valid_ids = match_avg_rank[match_avg_rank <= RANK_THRESHOLD].index
        df = df[df["Match ID"].isin(valid_ids)].copy()
        print(f"Rank filter (<= {RANK_THRESHOLD}): {len(valid_ids)} matches remain")

        df["is_win"] = df.apply(_is_win, axis=1)
        df["kda_ratio"] = df["K/D/A"].apply(_kda)

        hero_df = build_hero_stats(df)
        hero_df.to_csv("hero_stats.csv", index=False, sep=";", encoding="utf-8-sig")
        print(f"Saved hero_stats.csv ({len(hero_df)} heroes)")

        player_df = build_player_stats(df)
        player_df.to_csv("player_stats.csv", index=False, sep=";", encoding="utf-8-sig")
        print(f"Saved player_stats.csv ({len(player_df)} players)")

    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    run()
    input("\nPress Enter to exit...")
