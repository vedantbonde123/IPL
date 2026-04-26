#!/usr/bin/env python3
"""
IPL Fantasy Draft League — Auto PTS Updater
Fetches latest OverallPoints from IPL Fantasy API and patches index.html
"""

import json
import re
import sys
import requests
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────────────────────────
API_URL = "https://fantasy.iplt20.com/classic/api/feed/gamedayplayers"
API_PARAMS = {
    "lang": "en",
    # tourgamedayId & teamgamedayId are discovered automatically (see fetch_api)
}
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://fantasy.iplt20.com/",
    "Accept": "application/json",
}

# Name map: draft name → API name (only where they differ)
NAME_MAP = {
    "Varun Chakravarthy":  "Varun Chakaravarthy",
    "Vaibhav Suryavanshi": "Vaibhav Sooryavanshi",
}

DRAFT = {
    "Vivek":    [
        "Rohit Sharma","KL Rahul","Ishan Kishan","Arshdeep Singh","Mitchell Marsh",
        "Noor Ahmad","Prabhsimran Singh","Finn Allen","Marco Jansen","Rashid Khan",
        "Nitish Rana","Lungi Ngidi","Jofra Archer","Angkrish Raghuvanshi","Prashant Veer",
    ],
    "Vedant":   [
        "Virat Kohli","Suryakumar Yadav","Shubman Gill","Nicholas Pooran","Rajat Patidar",
        "Jos Buttler","Mohammed Siraj","Priyansh Arya","Sunil Narine","Ajinkya Rahane",
        "Khaleel Ahmed","Krunal Pandya","Yuzvendra Chahal","Ayush Badoni","Prithvi Shaw",
    ],
    "Ayushman": [
        "Sanju Samson","Hardik Pandya","Travis Head","Vaibhav Suryavanshi","Axar Patel",
        "Aiden Markram","Varun Chakravarthy","Ravindra Jadeja","Kuldeep Yadav","Shivam Dube",
        "Will Jacks","Quinton de Kock","Mitchell Santner","Washington Sundar","Deepak Chahar",
    ],
    "Niranjan": [
        "Sai Sudharsan","Yashasvi Jaiswal","Ruturaj Gaikwad","Phil Salt","Cameron Green",
        "Trent Boult","Riyan Parag","Ayush Mhatre","Harshal Patel","Tristan Stubbs",
        "Kagiso Rabada","Dhruv Jurel","Jacob Bethell","Karun Nair","Marcus Stoinis",
    ],
    "Viraj":    [
        "Jasprit Bumrah","Abhishek Sharma","Shreyas Iyer","Rishabh Pant","Dewald Brevis",
        "Tilak Varma","Bhuvneshwar Kumar","Shimron Hetmyer","Heinrich Klaasen","Avesh Khan",
        "Nehal Wadhera","Prasidh Krishna","Shashank Singh","Mohammad Shami","Pat Cummins",
    ],
}

# ── FETCH ────────────────────────────────────────────────────────────────────
def fetch_api(gameday_id=None):
    """
    Fetch player data from IPL Fantasy API.
    If gameday_id is not supplied, tries IDs 30-50 until one returns players.
    Returns list of player dicts.
    """
    if gameday_id:
        ids = [int(gameday_id)]
    else:
        ids = list(range(30, 55))

    for gd in ids:
        params = {**API_PARAMS, "tourgamedayId": gd, "teamgamedayId": gd}
        try:
            r = requests.get(API_URL, params=params, headers=API_HEADERS, timeout=15)
            if r.status_code != 200:
                continue
            data = r.json()
            players = data.get("Data", {}).get("Value", {}).get("Players", [])
            if players:
                print(f"[INFO] Fetched {len(players)} players at gameday {gd} "
                      f"(PlyrGamedayId={players[0].get('PlyrGamedayId')})")
                return players, gd
        except Exception as e:
            print(f"[WARN] gameday {gd}: {e}")
            continue

    raise RuntimeError("Could not fetch player data for any gameday ID")


# ── PARSE ────────────────────────────────────────────────────────────────────
def build_pts_map(players):
    """Build {api_name: overall_points} from API response."""
    return {p["Name"]: int(p.get("OverallPoints", 0) or 0) for p in players}


def get_pts(pts_map, draft_name):
    api_name = NAME_MAP.get(draft_name, draft_name)
    return pts_map.get(api_name, None)


def validate(pts_map):
    missing = []
    for owner, roster in DRAFT.items():
        for player in roster:
            if get_pts(pts_map, player) is None:
                missing.append(f"{owner}: {player}")
    if missing:
        print("[WARN] Missing players in API response:")
        for m in missing:
            print(f"  {m}")
    else:
        print("[INFO] All 75 draft players found ✅")
    return missing


# ── PATCH index.html ──────────────────────────────────────────────────────────
def build_pts_block(pts_map, gameday_id):
    label = f"Season (M1-M{gameday_id})"
    lines = [
        f'const MATCHES = ["M1-M{gameday_id}"];',
        f'const MLABELS = ["{label}"];',
        "const PTS = {",
    ]
    for owner, roster in DRAFT.items():
        lines.append(f"  // --- {owner} ---")
        for player in roster:
            pts = get_pts(pts_map, player)
            if pts is None:
                pts = 0
            lines.append(f'  "{player}": [{pts}],')
    lines.append("};")
    return "\n".join(lines)


def patch_html(html: str, pts_map: dict, gameday_id: int) -> str:
    new_block = build_pts_block(pts_map, gameday_id)

    # Replace block between const MATCHES and closing }; of const PTS
    pattern = (
        r'const MATCHES\s*=\s*\[.*?\];'   # MATCHES line
        r'.*?'                              # anything (MLABELS, etc.)
        r'const PTS\s*=\s*\{.*?\};'        # full PTS block
    )
    replacement = new_block

    new_html, n = re.subn(pattern, replacement, html, count=1, flags=re.DOTALL)
    if n == 0:
        raise RuntimeError("Could not find const PTS block in index.html — pattern mismatch")
    print(f"[INFO] Patched const MATCHES / MLABELS / PTS block (gameday {gameday_id})")
    return new_html


# ── STANDINGS ────────────────────────────────────────────────────────────────
def print_standings(pts_map):
    standings = []
    for owner, roster in DRAFT.items():
        total = sum(get_pts(pts_map, p) or 0 for p in roster)
        standings.append((owner, total))
    standings.sort(key=lambda x: -x[1])
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    print("\n── STANDINGS ───────────────────────────────")
    for i, (owner, total) in enumerate(standings):
        print(f"  {medals[i]}  {owner}: {total}")
    print("────────────────────────────────────────────\n")


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="index.html", help="Path to index.html")
    parser.add_argument("--gameday", type=int, default=None,
                        help="Override gameday ID (auto-detect if omitted)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print new PTS block but don't write file")
    args = parser.parse_args()

    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}] Starting update…")

    players, gd = fetch_api(args.gameday)
    pts_map = build_pts_map(players)
    missing = validate(pts_map)
    print_standings(pts_map)

    if args.dry_run:
        print(build_pts_block(pts_map, gd))
        return

    with open(args.file, "r", encoding="utf-8") as f:
        html = f.read()

    new_html = patch_html(html, pts_map, gd)

    if new_html == html:
        print("[INFO] No changes detected — file unchanged.")
        sys.exit(0)

    with open(args.file, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"[INFO] Written: {args.file}")
    # Signal to GitHub Actions that there are changes
    sys.exit(0)


if __name__ == "__main__":
    main()
