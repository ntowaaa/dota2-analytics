"""
Scrapes leaderboard ranks from Dotabuff for players in player_stats.csv.
Skips entries that already have a rank. Saves results to account_ranks_updated.csv.

Usage:
    pip install cloudscraper beautifulsoup4 pandas
    python scrape_ranks.py
"""

import time

import cloudscraper
import pandas as pd
from bs4 import BeautifulSoup

INPUT_FILE  = "player_stats.csv"
OUTPUT_FILE = "account_ranks_updated.csv"
REQUEST_DELAY = 1.0  # seconds between requests


def fetch_rank(scraper: cloudscraper.CloudScraper, account_id: str) -> str:
    url = f"https://www.dotabuff.com/players/{account_id}"
    try:
        resp = scraper.get(url, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            rank_div = soup.find("div", class_="leaderboard-rank-value")
            return rank_div.text.strip() if rank_div else "No Rank"
        if resp.status_code == 403:
            return "403 Forbidden"
        return f"HTTP {resp.status_code}"
    except Exception as exc:
        return f"Error: {exc}"


def main() -> None:
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "desktop": True}
    )

    try:
        df = pd.read_csv(INPUT_FILE, sep=";", encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(INPUT_FILE, sep=";", encoding="windows-1251")

    df.columns = df.columns.str.strip()
    df["AccountID_clean"] = (
        df["AccountID"].astype(str).str.replace(r"[^\d]", "", regex=True)
    )

    if "Rank" not in df.columns:
        df["Rank"] = ""
    df["Rank"] = df["Rank"].astype(str).replace("nan", "")

    print(f"Loaded {len(df)} rows from {INPUT_FILE}")
    skipped = 0
    processed = 0

    for idx, row in df.iterrows():
        acc_id = row["AccountID_clean"]
        rank = str(row["Rank"]).strip()

        if rank and rank.lower() not in ("", "no rank", "nan"):
            skipped += 1
            continue

        if not acc_id or acc_id == "nan":
            continue

        print(f"[{idx + 1}/{len(df)}] Fetching {acc_id}...", end=" ", flush=True)
        result = fetch_rank(scraper, acc_id)
        df.at[idx, "Rank"] = result
        processed += 1
        print(result)
        time.sleep(REQUEST_DELAY)

    df.drop(columns=["AccountID_clean"]).to_csv(
        OUTPUT_FILE, index=False, sep=";", encoding="utf-8-sig"
    )

    print(f"\nDone. Skipped: {skipped}, fetched: {processed}")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")
