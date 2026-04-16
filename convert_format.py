"""
Converts account_ranks_updated.csv (output of scrape_ranks.py)
into acc_id_ld_final.csv, which rank_merger.py uses as its ID->rank lookup.
"""

import pandas as pd

INPUT  = "account_ranks_updated.csv"
OUTPUT = "acc_id_ld_final.csv"


def main() -> None:
    df = pd.read_csv(INPUT, sep=";", encoding="utf-8-sig")

    result = df[["Никнейм", "AccountID", "Rank"]].copy()
    result.columns = ["Player Name", "AccountID", "LB Rank"]
    result["AccountID"] = result["AccountID"].astype(str).str.replace(r"[^\d]", "", regex=True)

    result.to_csv(OUTPUT, index=False, sep=";", encoding="utf-8-sig")
    print(f"Written {len(result)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
