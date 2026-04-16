"""
Checks each unique match ID in dota_matches_history_w_rank.csv against Dotabuff.
Matches that do NOT appear on Dotabuff are written to filtered_matches.csv
incrementally as they are found.

Usage:
    pip install cloudscraper pandas tqdm
    python check_dotabuff.py
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import cloudscraper
import pandas as pd
from tqdm import tqdm

INPUT_CSV  = "dota_matches_history_w_rank.csv"
OUTPUT_CSV = "filtered_matches.csv"
WORKERS    = 10
TIMEOUT    = 15
NOT_FOUND_MARKER = "DOTABUFF - Not Found"

_thread_local = threading.local()
_write_lock   = threading.Lock()


def _get_scraper() -> cloudscraper.CloudScraper:
    if not hasattr(_thread_local, "scraper"):
        _thread_local.scraper = cloudscraper.create_scraper()
    return _thread_local.scraper


def check_match(match_id: int) -> tuple[int, bool]:
    """Return (match_id, is_missing_from_dotabuff)."""
    url = f"https://www.dotabuff.com/matches/{match_id}"
    scraper = _get_scraper()
    while True:
        try:
            resp = scraper.get(url, timeout=TIMEOUT)
            if resp.status_code == 429:
                tqdm.write("  Rate limited, waiting 30s...")
                time.sleep(30)
                continue
            return match_id, NOT_FOUND_MARKER in resp.text
        except Exception as exc:
            tqdm.write(f"  Error for {match_id}: {exc}, skipping")
            return match_id, False


def main() -> None:
    print(f"Reading {INPUT_CSV}...")
    df = pd.read_csv(INPUT_CSV, sep=",", skiprows=1)
    df["Match ID"] = df["Match ID"].dropna().astype(int)
    unique_ids = df["Match ID"].unique()
    print(f"Unique matches: {len(unique_ids):,}  |  Workers: {WORKERS}")

    # Write header to output file
    df.iloc[0:0].to_csv(OUTPUT_CSV, sep=";", index=False, encoding="utf-8-sig")

    found = 0
    not_found = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(check_match, mid): mid for mid in unique_ids}
        with tqdm(as_completed(futures), total=len(unique_ids), unit="match") as bar:
            for future in bar:
                match_id, is_missing = future.result()
                if is_missing:
                    not_found += 1
                    rows = df[df["Match ID"] == match_id]
                    with _write_lock:
                        rows.to_csv(
                            OUTPUT_CSV, sep=";", index=False,
                            encoding="utf-8-sig", mode="a", header=False,
                        )
                else:
                    found += 1
                    tqdm.write(
                        f"  Found: {match_id}  "
                        f"https://www.dotabuff.com/matches/{match_id}"
                    )
                bar.set_postfix(found=found, missing=not_found)

    print(f"\nFound on Dotabuff: {found:,}  |  Missing: {not_found:,}")
    print(f"Output: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")
