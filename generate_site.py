"""
Static site generator for Dota 2 high-MMR match analytics.

Reads three CSV files produced by analytics.py, serialises them to JSON,
injects the data into an HTML template, and writes a single self-contained
index.html that can be opened in any browser.

Usage:
    python generate_site.py          # writes index.html next to this script
    python generate_site.py --out /path/to/index.html

Required files (relative to script directory):
    dota_matches_history_w_rank.csv
    hero_stats.csv
    player_stats.csv
    template.html                    # HTML/CSS/JS shell with __PLACEHOLDER__ tokens

Optional files (enable icons / facet data):
    hero_icons/          - hero portrait PNGs
    dota2_icons/         - item icon .webp/.png files
    facets_formatted.csv
    facet_icon_map.json
    items_data.json
    neutrals.json
"""

import argparse
import json
import os
from datetime import datetime
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def _path(*parts: str) -> str:
    return os.path.join(SCRIPT_DIR, *parts)


MATCHES_CSV    = _path("dota_matches_history_w_rank.csv")
HEROES_CSV     = _path("hero_stats.csv")
PLAYERS_CSV    = _path("player_stats.csv")
TEMPLATE_FILE  = _path("template.html")
ICONS_DIR      = _path("hero_icons")
ITEM_ICONS_DIR = _path("dota2_icons")
FACETS_CSV     = _path("facets_formatted.csv")
FACET_MAP_JSON = _path("facet_icon_map.json")
ITEMS_JSON     = _path("items_data.json")
NEUTRALS_JSON  = _path("neutrals.json")


# ---------------------------------------------------------------------------
# Hero name normalisation
# Many heroes have an internal ID that differs from their display name.
# ALIAS maps variant/legacy IDs to a canonical key used in icon lookups.
# DISPLAY maps canonical keys to human-readable names shown in the UI.
# ---------------------------------------------------------------------------
ALIAS: dict[str, str] = {
    # Legacy internal names -> canonical
    "doom_bringer":       "doom",
    "furion":             "natures_prophet",
    "life_stealer":       "lifestealer",
    "magnataur":          "magnus",
    "necrolyte":          "necrophos",
    "nevermore":          "shadow_fiend",
    "queenofpain":        "qop",
    "shredder":           "timbersaw",
    "treant":             "treant_protector",
    "vengefulspirit":     "vengeful_spirit",
    "windrunner":         "windranger",
    "zuus":               "zeus",
    # Modern aliases -> canonical short keys
    "anti_mage":          "antimage",
    "centaur_warrunner":  "centaur",
    "clockwerk":          "rattletrap",
    "io":                 "wisp",
    "outworld_destroyer": "obsidian_destroyer",
    "phantom_assassin":   "pa",
    "queen_of_pain":      "qop",
    "skywrath_mage":      "skywrath",
    "templar_assassin":   "ta",
    "underlord":          "abyssal_underlord",
    "wraith_king":        "skeleton_king",
}

DISPLAY: dict[str, str] = {
    "abyssal_underlord":  "Underlord",
    "antimage":           "Anti-Mage",
    "centaur":            "Centaur Warrunner",
    "doom":               "Doom",
    "lifestealer":        "Lifestealer",
    "magnus":             "Magnus",
    "natures_prophet":    "Nature's Prophet",
    "necrophos":          "Necrophos",
    "obsidian_destroyer": "Outworld Destroyer",
    "pa":                 "Phantom Assassin",
    "qop":                "Queen of Pain",
    "rattletrap":         "Clockwerk",
    "shadow_fiend":       "Shadow Fiend",
    "skeleton_king":      "Wraith King",
    "skywrath":           "Skywrath Mage",
    "ta":                 "Templar Assassin",
    "timbersaw":          "Timbersaw",
    "treant_protector":   "Treant Protector",
    "vengeful_spirit":    "Vengeful Spirit",
    "windranger":         "Windranger",
    "wisp":               "Io",
    "zeus":               "Zeus",
    # Common multi-word heroes
    "arc_warden":         "Arc Warden",
    "bounty_hunter":      "Bounty Hunter",
    "crystal_maiden":     "Crystal Maiden",
    "dark_seer":          "Dark Seer",
    "dark_willow":        "Dark Willow",
    "death_prophet":      "Death Prophet",
    "dragon_knight":      "Dragon Knight",
    "drow_ranger":        "Drow Ranger",
    "earth_spirit":       "Earth Spirit",
    "elder_titan":        "Elder Titan",
    "ember_spirit":       "Ember Spirit",
    "faceless_void":      "Faceless Void",
    "keeper_of_the_light":"Keeper of the Light",
    "legion_commander":   "Legion Commander",
    "lone_druid":         "Lone Druid",
    "monkey_king":        "Monkey King",
    "naga_siren":         "Naga Siren",
    "night_stalker":      "Night Stalker",
    "nyx_assassin":       "Nyx Assassin",
    "ogre_magi":          "Ogre Magi",
    "phantom_lancer":     "Phantom Lancer",
    "primal_beast":       "Primal Beast",
    "sand_king":          "Sand King",
    "shadow_demon":       "Shadow Demon",
    "shadow_shaman":      "Shadow Shaman",
    "spirit_breaker":     "Spirit Breaker",
    "storm_spirit":       "Storm Spirit",
    "troll_warlord":      "Troll Warlord",
    "void_spirit":        "Void Spirit",
    "winter_wyvern":      "Winter Wyvern",
    "witch_doctor":       "Witch Doctor",
}

# Item name aliases: CSV internal name -> canonical icon key
ITEM_ALIAS: dict[str, str] = {
    "ancient_janggo":      "drum_of_endurance",
    "assault":             "assault_cuirass",
    "basher":              "skull_basher",
    "bfury":               "battle_fury",
    "blight_stone":        "orb_of_blight",
    "blink":               "blink_dagger",
    "boots":               "boots_of_speed",
    "boots_of_elves":      "slippers_of_agility",
    "branches":            "iron_branch",
    "cyclone":             "euls_scepter_of_divinity",
    "dust":                "dust_of_appearance",
    "eagle":               "eaglesong",
    "famango":             "enchanted_mango",
    "gauntlets":           "gauntlets_of_strength",
    "ghost":               "ghost_scepter",
    "gloves":              "gloves_of_haste",
    "infused_raindrop":    "infused_raindrops",
    "invis_sword":         "shadow_blade",
    "manta":               "manta_style",
    "pers":                "perseverance",
    "pipe":                "pipe_of_insight",
    "sobi_mask":           "sages_mask",
    "ultimate_scepter":    "aghanims_scepter",
    "vladmir":             "vladmirs_offering",
    "ward_dispenser":      "observer_and_sentry_wards",
    "ward_observer":       "observer_ward",
    "ward_sentry":         "sentry_ward",
}


# ---------------------------------------------------------------------------
# Item index (built during data processing, shared across methods)
# ---------------------------------------------------------------------------
_item_dict:    dict[str, int] = {}
_item_names:   list[str]      = []
_item_neutral: list[bool]     = []


def _item_index(name: str, is_neutral: bool = False) -> int:
    if name not in _item_dict:
        _item_dict[name] = len(_item_names)
        _item_names.append(name)
        _item_neutral.append(is_neutral)
    return _item_dict[name]


def _parse_items(items_str: str) -> list[int]:
    """
    Parse a comma-separated item string like 'magic_wand, blink, [vambrace]'
    into a list of canonical item indices.
    Neutral items are wrapped in square brackets in the CSV.
    """
    if not items_str or str(items_str).strip().lower() == "nan":
        return []
    result = []
    for token in str(items_str).split(","):
        token = token.strip()
        if not token:
            continue
        is_neutral = token.startswith("[") and token.endswith("]")
        name = token[1:-1] if is_neutral else token
        canonical = ITEM_ALIAS.get(name, name)
        result.append(_item_index(canonical, is_neutral))
    return result


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def normalize(name: str) -> str:
    return (name or "").lower().strip().replace(" ", "_").replace("-", "_").replace("'", "")


def _display_name(raw: str) -> str:
    key = normalize(raw)
    if key in DISPLAY:
        return DISPLAY[key]
    return raw.replace("_", " ").title()


def _hero_canon(raw: str) -> str:
    key = normalize(raw)
    return ALIAS.get(key, key)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_csvs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    matches = pd.read_csv(MATCHES_CSV, sep=";", skiprows=1, encoding="utf-8-sig")
    heroes  = pd.read_csv(HEROES_CSV,  sep=";",             encoding="utf-8-sig")
    players = pd.read_csv(PLAYERS_CSV, sep=";",             encoding="utf-8-sig")
    return matches, heroes, players


def load_hero_icons() -> dict[str, str]:
    """Return {normalized_hero_name: relative_path} for all PNG files in hero_icons/."""
    icons: dict[str, str] = {}
    if not os.path.isdir(ICONS_DIR):
        print(f"[warn] hero_icons/ not found at {ICONS_DIR}")
        return icons
    for fname in os.listdir(ICONS_DIR):
        if not fname.endswith(".png"):
            continue
        raw = fname.replace("_icon_dota2_gameasset.png", "").replace("120px-", "")
        icons[normalize(raw)] = f"hero_icons/{fname}"
    print(f"[info] {len(icons)} hero icons loaded")
    return icons


def build_icon_lookup(icons: dict[str, str]) -> dict[str, str]:
    """
    Expand the raw icon dict so that both the canonical name and all aliases
    resolve to the same image path. This avoids 404s for legacy hero IDs.
    """
    lookup = dict(icons)
    for old, new in list(ALIAS.items()):
        a, c = normalize(old), normalize(new)
        if c in icons and a not in lookup:
            lookup[a] = icons[c]
        if a in icons and c not in lookup:
            lookup[c] = icons[a]
    return lookup


def load_item_icons() -> dict[str, str]:
    """Return {canonical_item_name: relative_path}, preferring .webp over .png."""
    icons: dict[str, str] = {}
    if not os.path.isdir(ITEM_ICONS_DIR):
        print(f"[warn] dota2_icons/ not found")
        return icons
    for fname in os.listdir(ITEM_ICONS_DIR):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in (".webp", ".png", ".jpg"):
            continue
        key = os.path.splitext(fname)[0]
        if key not in icons or ext == ".webp":
            icons[key] = f"dota2_icons/{fname}"
    print(f"[info] {len(icons)} item icons loaded")
    return icons


def load_item_meta() -> dict[str, dict]:
    """
    Return {canonical_item_name: {display, price, tier}} from items_data.json
    and neutrals.json.
    """
    meta: dict[str, dict] = {}

    def _norm_display(s: str) -> str:
        return s.lower().strip().replace(" ", "_").replace("'", "").replace("-", "_")

    if os.path.exists(ITEMS_JSON):
        with open(ITEMS_JSON, encoding="utf-8") as f:
            data = json.load(f)
        for item in data.get("items", []):
            key = _norm_display(item["name"])
            meta[key] = {"display": item["name"], "price": item.get("price", 0), "tier": None}
        print(f"[info] {len(meta)} items from items_data.json")

    if os.path.exists(NEUTRALS_JSON):
        with open(NEUTRALS_JSON, encoding="utf-8") as f:
            ndata = json.load(f)
        for tier_key, names in ndata.get("neutral_items", {}).items():
            tier = int(tier_key.split("_")[1])
            for display in names:
                key = _norm_display(display)
                entry = meta.get(key, {"display": display, "price": 0})
                entry.update({"tier": tier, "display": display})
                meta[key] = entry

    return meta


def load_facet_names() -> dict[str, dict[str, str]]:
    """Return {normalized_hero: {F1: 'Facet Name', F2: 'Facet Name', ...}}."""
    if not os.path.exists(FACETS_CSV):
        print("[warn] facets_formatted.csv not found")
        return {}
    df = pd.read_csv(FACETS_CSV, sep=";", encoding="utf-8-sig")
    result: dict[str, dict] = {}
    for _, row in df.iterrows():
        hero_raw  = normalize(str(row["Герой"]))
        hero_key  = ALIAS.get(hero_raw, hero_raw)
        facet_num = str(row["Номер фасета"]).strip()
        name      = str(row["Название"]).strip()
        result.setdefault(hero_key, {})[facet_num] = name
        if hero_raw != hero_key:
            result.setdefault(hero_raw, {})[facet_num] = name
    return result


def load_facet_icon_map() -> dict[str, dict[str, str]]:
    """Return {hero_key: {facet_name: icon_filename_no_ext}}."""
    if not os.path.exists(FACET_MAP_JSON):
        print("[warn] facet_icon_map.json not found")
        return {}
    with open(FACET_MAP_JSON, encoding="utf-8") as f:
        raw: dict = json.load(f)
    # Resolve aliases so both old and new hero keys point to the same data.
    # Two passes handle transitive chains.
    for _ in range(2):
        for old, new in ALIAS.items():
            data = raw.get(old) or raw.get(new)
            if data:
                raw.setdefault(old, data)
                raw.setdefault(new, data)
    return raw


# ---------------------------------------------------------------------------
# Data builders
# ---------------------------------------------------------------------------

def build_matches(df: pd.DataFrame) -> list[dict]:
    """
    Convert the raw match CSV into a list of match dicts for the frontend.
    Matches where the NW leader contradicts the Radiant Win Chance are skipped
    (they were likely recorded mid-game, before a lead change).
    """
    records = []
    for match_id, group in df.groupby("Match ID"):
        row0      = group.iloc[0]
        nw_lead   = str(row0["NW Lead"])
        try:
            rwc = float(str(row0["Radiant Win Chance %"]).strip())
        except (ValueError, TypeError):
            rwc = 50.0

        # Determine which team was ahead by net worth
        if "Radiant" in nw_lead and "+" in nw_lead:
            nw_leader = "radiant"
        elif "Dire" in nw_lead and "+" in nw_lead:
            nw_leader = "dire"
        else:
            continue  # ambiguous, skip

        rwc_leader = "radiant" if rwc > 50 else "dire"
        if nw_leader != rwc_leader:
            continue  # NW and win-probability disagree, skip

        winner = nw_leader

        def _player_list(sub: pd.DataFrame, team: str) -> list[dict]:
            players = []
            for _, r in sub.sort_values("Role").iterrows():
                try:
                    aid = int(str(r.get("AccountID", "")).strip().replace("\t", ""))
                except (ValueError, TypeError):
                    aid = None
                try:
                    facet = int(r["Facet"])
                except (ValueError, TypeError):
                    facet = None
                rk = r["LB Rank"]
                players.append({
                    "name":  str(r["Player Name"]),
                    "hero":  _hero_canon(str(r["Hero"])),
                    "kda":   str(r["K/D/A"]),
                    "nw":    int(r["Net Worth"]),
                    "rank":  int(rk) if pd.notna(rk) else None,
                    "role":  int(r["Role"]),
                    "level": int(r["Level"]),
                    "aid":   aid,
                    "team":  team,
                    "facet": facet,
                    "won":   1 if team == winner else 0,
                    "items": _parse_items(str(r.get("Items", ""))),
                })
            return players

        radiant = group[group["Team"] == "Radiant"]
        dire    = group[group["Team"] == "Dire"]
        ranks   = [r["LB Rank"] for _, r in group.iterrows() if pd.notna(r["LB Rank"])]
        avg_rank = round(sum(ranks) / len(ranks), 1) if ranks else None

        records.append({
            "id":       int(match_id),
            "date":     str(row0["Date"]),
            "duration": str(row0["Game Time"]),
            "radiant":  _player_list(radiant, "radiant"),
            "dire":     _player_list(dire, "dire"),
            "nw_lead":  str(row0["NW Lead"]),
            "avg_rank": avg_rank,
            "rwc":      rwc,
            "winner":   winner,
        })

    records.sort(key=lambda m: m["date"], reverse=True)
    return records


def build_heroes(df: pd.DataFrame) -> list[dict]:
    """Build the hero stats list, deduplicating by keeping the row with more games."""
    seen: dict[str, int] = {}   # hero key -> games count
    records: list[dict]  = []

    for _, row in df.iterrows():
        name  = str(row["Герой"])
        games = int(row["Игры"])
        key   = name.lower().strip()

        if key in seen:
            if games <= seen[key]:
                continue
            records = [h for h in records if h["name"].lower().strip() != key]

        seen[key] = games
        try:
            wr = float(str(row["WR"]).replace("%", "").strip())
        except ValueError:
            wr = 0.0

        records.append({
            "name":   name,
            "games":  games,
            "wr":     wr,
            "wr_str": str(row["WR"]),
            "kda":    float(row["KDA"]),
            "nw":     int(row["NW"]),
            "pos1":   str(row["Поз 1"]),
            "pos2":   str(row["Поз 2"]),
            "pos3":   str(row["Поз 3"]),
            "pos4":   str(row["Поз 4"]),
            "pos5":   str(row["Поз 5"]),
            "facets": str(row["Фасеты"]),
            "top":    str(row["Топ игроки"]),
        })

    records.sort(key=lambda h: h["games"], reverse=True)
    return records


def build_players(df: pd.DataFrame) -> list[dict]:
    records = []
    for _, row in df.iterrows():
        try:
            wr = float(str(row["WR"]).replace("%", "").strip())
        except ValueError:
            wr = 0.0
        rk      = row["Rank"]
        aid_raw = row.get("AccountID")
        try:
            aid = int(str(aid_raw).strip().replace("\t", "")) if pd.notna(aid_raw) else None
        except (ValueError, TypeError):
            aid = None

        records.append({
            "name":       str(row["Никнейм"]),
            "rank":       int(rk) if pd.notna(rk) else None,
            "team":       str(row["Team"]) if pd.notna(row.get("Team")) else "",
            "games":      int(row["Игры"]),
            "wr":         wr,
            "kda":        float(row["KDA"]),
            "nw":         int(row["NW"]),
            "heroes":     str(row["Герои (по убыванию)"]),
            "account_id": aid,
        })

    records.sort(key=lambda p: (p["rank"] is None, p["rank"] or 9999))
    return records


# ---------------------------------------------------------------------------
# Site generation
# ---------------------------------------------------------------------------

def generate(out_path: str) -> None:
    print("[info] Loading CSVs...")
    matches_df, heroes_df, players_df = load_csvs()

    print("[info] Building data structures...")
    match_data  = build_matches(matches_df)
    hero_data   = build_heroes(heroes_df)
    player_data = build_players(players_df)

    print("[info] Loading icons and metadata...")
    raw_icons   = load_hero_icons()
    icon_lookup = build_icon_lookup(raw_icons)
    item_icons  = load_item_icons()
    item_meta   = load_item_meta()
    facet_names = load_facet_names()
    facet_icons = load_facet_icon_map()

    # Build display-name table for the frontend
    disp_table: dict[str, str] = {normalize(h["name"]): _display_name(h["name"]) for h in hero_data}
    disp_table.update(DISPLAY)

    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Load HTML template
    if not os.path.exists(TEMPLATE_FILE):
        raise FileNotFoundError(
            f"template.html not found at {TEMPLATE_FILE}. "
            "See README for how to obtain or generate it."
        )
    with open(TEMPLATE_FILE, encoding="utf-8") as f:
        html = f.read()

    substitutions = {
        "__ICONS__":       json.dumps(icon_lookup,  ensure_ascii=False),
        "__MATCHES__":     json.dumps(match_data,   ensure_ascii=False),
        "__HEROES__":      json.dumps(hero_data,    ensure_ascii=False),
        "__PLAYERS__":     json.dumps(player_data,  ensure_ascii=False),
        "__DISP__":        json.dumps(disp_table,   ensure_ascii=False),
        "__FACETS__":      json.dumps(facet_names,  ensure_ascii=False),
        "__FACET_ICONS__": json.dumps(facet_icons,  ensure_ascii=False),
        "__ITEM_NAMES__":  json.dumps(_item_names,  ensure_ascii=False),
        "__ITEM_NEUTRAL__":json.dumps(_item_neutral, ensure_ascii=False),
        "__ITEM_ICONS__":  json.dumps(item_icons,   ensure_ascii=False),
        "__ITEM_META__":   json.dumps(item_meta,    ensure_ascii=False),
        "__GENERATED__":   generated,
    }
    for placeholder, value in substitutions.items():
        html = html.replace(placeholder, value)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = os.path.getsize(out_path) // 1024
    print(f"[done] {out_path} — {size_kb} KB")
    print(f"       {len(match_data)} matches | {len(hero_data)} heroes | {len(player_data)} players")
    print(f"       Generated: {generated}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Dota 2 analytics site")
    parser.add_argument("--out", default=_path("index.html"), help="Output HTML path")
    args = parser.parse_args()
    generate(args.out)


if __name__ == "__main__":
    main()
