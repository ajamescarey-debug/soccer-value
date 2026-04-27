"""
FBref scraper.

Fetches team-level xG and xGA from FBref league pages and converts
them into TeamStrength records.

Notes on FBref:
  - Be respectful: one request per league per day is fine
  - Use a real user-agent or you'll get blocked instantly
  - Some tables are wrapped in HTML comments; we extract them
  - If FBref restructures HTML, the parser returns empty and the
    pipeline skips the league rather than crashing
"""

import re
from typing import Dict, Optional, Tuple

import requests
from bs4 import BeautifulSoup, Comment

from . import config
from . import data
from .model import TeamStrength


# League key -> (FBref comp ID, slug)
FBREF_LEAGUE_MAP: Dict[str, Tuple[int, str]] = {
    "soccer_netherlands_eredivisie": (23, "Eredivisie"),
    "soccer_belgium_first_div": (37, "Belgian-Pro-League"),
    "soccer_portugal_primeira_liga": (32, "Primeira-Liga"),
    "soccer_spl": (40, "Scottish-Premiership"),
    "soccer_usa_mls": (22, "Major-League-Soccer"),
    "soccer_japan_j_league": (25, "J1-League"),
    "soccer_brazil_campeonato": (24, "Serie-A"),
}

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _fetch_page(url: str, timeout: int = 30) -> Optional[str]:
    """Fetch an FBref page. Returns HTML or None on failure."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        if resp.status_code != 200:
            print(f"[fbref] {url} returned {resp.status_code}")
            return None
        return resp.text
    except requests.RequestException as e:
        print(f"[fbref] request failed: {e}")
        return None


def _unwrap_comments(soup: BeautifulSoup) -> BeautifulSoup:
    """
    FBref wraps some tables in HTML comments to defeat naive scrapers.
    Extract any tables hiding inside comments and append them to the soup.
    """
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        text = str(comment)
        if "<table" in text:
            inner = BeautifulSoup(text, "lxml")
            soup.append(inner)
    return soup


def _cell_value(row, names) -> Optional[str]:
    """
    Find a cell by data-stat, trying multiple possible names.
    FBref has changed naming conventions over time; we try alternatives.
    """
    for name in names:
        cell = row.find(["td", "th"], {"data-stat": name})
        if cell:
            text = cell.get_text(strip=True)
            if text:
                return text
    return None


def _parse_squad_table(html: str) -> Dict[str, dict]:
    """
    Parse the Squad Standard Stats table.
    Returns {team_name: {"mp": int, "xg": float, "xga": float}}.
    """
    soup = BeautifulSoup(html, "lxml")
    soup = _unwrap_comments(soup)

    # The squad-stats-for table — handles both naming conventions
    table = (
        soup.find("table", id=re.compile(r"stats_squads_standard_for"))
        or soup.find("table", id=re.compile(r"stats_teams_standard_for"))
        or soup.find("table", id=re.compile(r"stats_squads_standard"))
    )
    if not table:
        print("[fbref] no squad standard table found")
        return {}

    tbody = table.find("tbody")
    if not tbody:
        return {}

    teams: Dict[str, dict] = {}
    for row in tbody.find_all("tr"):
        # Skip section header rows
        classes = row.get("class") or []
        if "thead" in classes:
            continue

        team_name = _cell_value(row, ["team", "squad"])
        if not team_name:
            continue

        mp_str = _cell_value(row, ["games"])
        xg_str = _cell_value(row, ["xg_for", "xg"])
        xga_str = _cell_value(row, ["xg_against", "xga"])

        try:
            teams[team_name] = {
                "mp": int(mp_str) if mp_str else 0,
                "xg": float(xg_str) if xg_str else 0.0,
                "xga": float(xga_str) if xga_str else 0.0,
            }
        except ValueError:
            print(f"[fbref] couldn't parse stats for {team_name}: "
                  f"mp={mp_str} xg={xg_str} xga={xga_str}")
            continue

    return teams


def fetch_strengths(league_key: str) -> Dict[str, TeamStrength]:
    """
    Fetch team strengths for one league from FBref.
    Returns empty dict on any failure — pipeline handles empty cleanly.
    """
    if league_key not in FBREF_LEAGUE_MAP:
        return {}

    comp_id, slug = FBREF_LEAGUE_MAP[league_key]
    url = f"https://fbref.com/en/comps/{comp_id}/{slug}-Stats"

    html = _fetch_page(url)
    if not html:
        return {}

    raw = _parse_squad_table(html)
    if not raw:
        return {}

    strengths: Dict[str, TeamStrength] = {}
    for team_name, stats in raw.items():
        mp = stats["mp"]
        if mp < 3:
            # Too few games for a meaningful average — skip
            continue
        strengths[team_name] = TeamStrength(
            xg_for_per_game=round(stats["xg"] / mp, 4),
            xg_against_per_game=round(stats["xga"] / mp, 4),
            games_in_sample=mp,
        )
    return strengths


def main():
    """CLI: python -m src.fbref soccer_netherlands_eredivisie"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.fbref <league_key>")
        print("\nAvailable leagues:")
        for key in FBREF_LEAGUE_MAP:
            print(f"  {key}")
        sys.exit(1)

    league_key = sys.argv[1]
    if league_key not in FBREF_LEAGUE_MAP:
        print(f"Unknown league: {league_key}")
        sys.exit(1)

    print(f"Fetching {league_key} from FBref...")
    strengths = fetch_strengths(league_key)

    if not strengths:
        print("\nNo data fetched. Possible causes:")
        print("  - FBref blocked the request (try again in a few minutes)")
        print("  - Page structure changed (parser needs updating)")
        print("  - League key not mapped")
        sys.exit(1)

    print(f"\nGot {len(strengths)} teams:\n")
    for team, s in sorted(strengths.items()):
        print(f"  {team:30s}  {s.games_in_sample:2d} games  "
              f"xG/g {s.xg_for_per_game:.2f}  "
              f"xGA/g {s.xg_against_per_game:.2f}")

    data.save_team_strengths(league_key, strengths)
    print(f"\nSaved to data/{league_key}_strengths.json")


if __name__ == "__main__":
    main()
