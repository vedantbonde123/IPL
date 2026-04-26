#!/usr/bin/env python3
"""
IPL Fantasy Draft League — Auto PTS Updater
Fetches latest OverallPoints from IPL Fantasy API and patches index.html
"""

import re
import sys
import requests
from datetime import datetime

# ── CONFIG ───────────────────────────────────────────────────────────────────
API_URL = "https://fantasy.iplt20.com/classic/api/feed/gamedayplayers"
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://fantasy.iplt20.com/",
    "Accept": "application/json",
}

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

# ── FETCH ─────────────────────────────────────────────────────────────────────
def fetch_api(gameday_id=None):
    """
    Scans gameday IDs HIGH → LOW (55 down to 1) to find the LATEST one with data.
    The actual match number comes from PlyrGamedayId inside the response,
    NOT from the tourgamedayId we queried with — so the label is always accurate.
    """
    if gameday_id:
        ids = [int(gameday_id)]
    else:
        ids = list(range(55, 0, -1))  # highest first → always gets latest

    best_players = None
    best_gd = None
    best_match_id = -1
    consecutive_empty = 0

    for gd in ids:
        params = {"lang": "en", "tourgamedayId": gd, "teamgamedayId": gd}
        try:
            r = requests.get(API_URL, params=params, headers=API_HEADERS, timeout=15)
            if r.status_code != 200:
                consecutive_empty += 1
            else:
                data = r.json()
                players = data.get("Data", {}).get("Value", {}).get("Players", [])
                if not players:
                    consecutive_empty += 1
                else:
                    consecutive_empty = 0
                    match_id = players[0].get("PlyrGamedayId", 0)
                    print(f"[INFO] gameday {gd} → PlyrGamedayId={match_id}, players={len(players)}")
                    if match_id > best_match_id:
                        best_match_id = match_id
                        best_players = players
                        best_gd = gd
                    # Once we've found data and seen 5 empty IDs below it, stop
                    if best_match_id > 0 and consecutive_empty >= 5:
                        break
        except Exception as e:
            print(f"[WARN] gameday {gd}: {e}")
            consecutive_empty += 1
            continue

    if not best_players:
        raise RuntimeError("Could not fetch player data for any gameday ID")

    print(f"[INFO] Using gameday {best_gd} (PlyrGamedayId={best_match_id})")
    return best_players, best_match_id  # match_id used as label, e.g. M37


# ── PARSE ─────────────────────────────────────────────────────────────────────
def build_pts_map(players):
    return {p["Name"]: int(p.get("OverallPoints", 0) or 0) for p in players}


def get_pts(pts_map, draft_name):
    return pts_map.get(NAME_MAP.get(draft_name, draft_name), None)


def validate(pts_map):
    missing = []
    for owner, roster in DRAFT.items():
        for player in roster:
            if get_pts(pts_map, player) is None:
                missing.append(f"{owner}: {player}")
    if missing:
        print("[WARN] Missing players:")
        for m in missing:
            print(f"  {m}")
    else:
        print("[INFO] All 75 draft players found ✅")
    return missing


# ── PATCH index.html ──────────────────────────────────────────────────────────
def build_pts_block(pts_map, match_id):
    label = f"Season (M1-M{match_id})"
    lines = [
        f'const MATCHES = ["M1-M{match_id}"];',
        f'const MLABELS = ["{label}"];',
        "const PTS = {",
    ]
    for owner, roster in DRAFT.items():
        lines.append(f"  // --- {owner} ---")
        for player in roster:
            pts = get_pts(pts_map, player) or 0
            lines.append(f'  "{player}": [{pts}],')
    lines.append("};")
    return "\n".join(lines)


def patch_html(html, pts_map, match_id):
    new_block = build_pts_block(pts_map, match_id)
    pattern = (
        r'const MATCHES\s*=\s*\[.*?\];'
        r'.*?'
        r'const PTS\s*=\s*\{.*?\};'
    )
    new_html, n = re.subn(pattern, new_block, html, count=1, flags=re.DOTALL)
    if n == 0:
        raise RuntimeError("Could not find const PTS block in index.html — pattern mismatch")
    print(f"[INFO] Patched MATCHES/MLABELS/PTS → M{match_id}")
    return new_html


# ── STANDINGS ─────────────────────────────────────────────────────────────────
def print_standings(pts_map):
    standings = [(o, sum(get_pts(pts_map, p) or 0 for p in r)) for o, r in DRAFT.items()]
    standings.sort(key=lambda x: -x[1])
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    print("\n── STANDINGS ───────────────────────────────")
    for i, (owner, total) in enumerate(standings):
        print(f"  {medals[i]}  {owner}: {total}")
    print("────────────────────────────────────────────\n")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="index.html")
    parser.add_argument("--gameday", type=int, default=None,
                        help="Force a specific gameday ID (auto-detect if omitted)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print new block without writing file")
    args = parser.parse_args()

    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}] Starting update…")

    players, match_id = fetch_api(args.gameday)
    pts_map = build_pts_map(players)
    validate(pts_map)
    print_standings(pts_map)

    if args.dry_run:
        print(build_pts_block(pts_map, match_id))
        return

    with open(args.file, "r", encoding="utf-8") as f:
        html = f.read()

    new_html = patch_html(html, pts_map, match_id)

    if new_html == html:
        print("[INFO] No changes — file unchanged.")
        sys.exit(0)

    with open(args.file, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"[INFO] Written: {args.file}")
    sys.exit(0)


if __name__ == "__main__":
    main()
