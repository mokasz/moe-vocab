#!/usr/bin/env python3
"""scrape_master.py — ターゲット1900単語リストをCSVに保存（一回限り）
Usage: venv/bin/python moe-vocab/scripts/scrape_master.py
Output: moe-vocab/data/target1900_raw.csv  (id, word, japanese)
"""
import csv, sys, time
from pathlib import Path
import requests
from bs4 import BeautifulSoup

OUTPUT = Path(__file__).parent.parent / "data" / "target1900_raw.csv"
URL = "https://ukaru-eigo.com/target-1900-word-list/"

def scrape():
    resp = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    rows = []
    for tr in soup.select("table tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue
        try:
            word_id = int(tds[1].get_text(strip=True))
        except ValueError:
            continue
        word = tds[2].get_text(strip=True)
        japanese = tds[3].get_text(strip=True)
        if word:
            rows.append({"id": word_id, "word": word, "japanese": japanese})
    return sorted(rows, key=lambda r: r["id"])

def main():
    rows = scrape()
    if not rows:
        print("ERROR: No rows found", file=sys.stderr); sys.exit(1)
    print(f"Found {len(rows)} words")
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "word", "japanese"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved to {OUTPUT}")

if __name__ == "__main__":
    main()
