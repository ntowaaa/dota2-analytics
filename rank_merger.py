"""
Merges match history files and fills in missing leaderboard ranks.

Sources:
  dota_matches_history.csv  - primary match log (from GSI server)
  filtered_matches.csv      - additional matches not yet on Dotabuff (optional)
  acc_id_ld.csv             - AccountID -> LB Rank lookup
  nickname_ld.csv           - Player Name -> LB Rank / LB Team lookup

Output:
  dota_matches_history_w_rank.csv
"""

import os
import traceback

import pandas as pd

HISTORY_FILE  = "dota_matches_history.csv"
FILTERED_FILE = "filtered_matches.csv"
ID_RANK_FILE  = "acc_id_ld.csv"
NICK_RANK_FILE = "nickname_ld.csv"
OUTPUT_FILE   = "dota_matches_history_w_rank.csv"


def _load_csv(path: str) -> pd.DataFrame:
    """Load a CSV regardless of whether it starts with a 'sep=;' directive."""
    with open(path, encoding="utf-8-sig") as f:
        first_line = f.readline().strip()
    skip = 1 if first_line.lower().startswith("sep=") else 0
    return pd.read_csv(path, sep=None, engine="python", skiprows=skip, encoding="utf-8-sig")


def _clean_account_id(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace("\t", ""), errors="coerce")


def run() -> None:
    if not os.path.exists(HISTORY_FILE):
        print(f"File not found: {HISTORY_FILE}")
        return

    try:
        print("Loading data...")
        df = _load_csv(HISTORY_FILE)
        df.columns = df.columns.str.strip()
        print(f"  {HISTORY_FILE}: {df['Match ID'].nunique():,} matches, {len(df):,} rows")

        if os.path.exists(FILTERED_FILE):
            df_extra = _load_csv(FILTERED_FILE)
            df_extra.columns = df_extra.columns.str.strip()
            print(f"  {FILTERED_FILE}: {df_extra['Match ID'].nunique():,} matches")
            before = df["Match ID"].nunique()
            df = pd.concat([df, df_extra], ignore_index=True)
            df = df.drop_duplicates(subset=["Match ID", "AccountID"], keep="first")
            added = df["Match ID"].nunique() - before
            print(f"  After merge: {df['Match ID'].nunique():,} unique matches (+{added:,})")
        else:
            print(f"  {FILTERED_FILE} not found, using {HISTORY_FILE} only")

        id_ranks   = pd.read_csv(ID_RANK_FILE,   sep=";", encoding="utf-8-sig")
        nick_ranks = pd.read_csv(NICK_RANK_FILE, sep=";", encoding="utf-8-sig")

        df["acc_clean"]       = _clean_account_id(df["AccountID"])
        id_ranks["acc_clean"] = _clean_account_id(id_ranks["AccountID"])

        id_rank_map  = dict(zip(id_ranks["acc_clean"], id_ranks["LB Rank"]))
        nick_rank_map = dict(zip(nick_ranks["Player Name"].str.strip(), nick_ranks["LB Rank"]))
        nick_team_map = dict(zip(nick_ranks["Player Name"].str.strip(), nick_ranks["LB Team"].fillna("")))

        def _fill_rank(row: pd.Series) -> pd.Series:
            rank = str(row["LB Rank"]).strip()
            team = str(row["LB Team"]).strip()
            # Skip rows that already have a rank
            if rank and rank.lower() not in ("nan", ""):
                return pd.Series([rank, team])
            name = str(row["Player Name"]).strip()
            new_rank = id_rank_map.get(row["acc_clean"], "") or nick_rank_map.get(name, "")
            new_team = nick_team_map.get(name, "")
            return pd.Series([new_rank, new_team])

        print("Filling missing ranks...")
        df[["LB Rank", "LB Team"]] = df.apply(_fill_rank, axis=1)

        # Restore AccountID with tab prefix (prevents Excel from mangling large ints)
        df["AccountID"] = df["acc_clean"].apply(
            lambda x: f"\t{int(x)}" if pd.notna(x) else ""
        )
        df = df.drop(columns=["acc_clean"])

        print(f"Writing {OUTPUT_FILE}...")
        with open(OUTPUT_FILE, "w", encoding="utf-8-sig", newline="") as f:
            f.write("sep=;\n")
            df.to_csv(f, index=False, sep=";", lineterminator="\n")

        print(f"Done. {df['Match ID'].nunique():,} matches saved.")

    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    run()
    input("\nPress Enter to exit...")
