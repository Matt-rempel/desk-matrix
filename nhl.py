"""Small, defensive adapter for the NHL's public schedule feed."""

from __future__ import annotations

from datetime import datetime, timezone

API = "https://api-web.nhle.com/v1"
TEAMS = (
    "ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET", "EDM",
    "FLA", "LAK", "MIN", "MTL", "NJD", "NSH", "NYI", "NYR", "OTT", "PHI", "PIT",
    "SEA", "SJS", "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH",
)
TEAM_NAMES = {
    "ANA": "Anaheim Ducks", "BOS": "Boston Bruins", "BUF": "Buffalo Sabres",
    "CAR": "Carolina Hurricanes", "CBJ": "Columbus Blue Jackets", "CGY": "Calgary Flames",
    "CHI": "Chicago Blackhawks", "COL": "Colorado Avalanche", "DAL": "Dallas Stars",
    "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers", "FLA": "Florida Panthers",
    "LAK": "Los Angeles Kings", "MIN": "Minnesota Wild", "MTL": "Montréal Canadiens",
    "NJD": "New Jersey Devils", "NSH": "Nashville Predators", "NYI": "New York Islanders",
    "NYR": "New York Rangers", "OTT": "Ottawa Senators", "PHI": "Philadelphia Flyers",
    "PIT": "Pittsburgh Penguins", "SEA": "Seattle Kraken", "SJS": "San Jose Sharks",
    "STL": "St. Louis Blues", "TBL": "Tampa Bay Lightning", "TOR": "Toronto Maple Leafs",
    "UTA": "Utah Mammoth", "VAN": "Vancouver Canucks", "VGK": "Vegas Golden Knights",
    "WPG": "Winnipeg Jets", "WSH": "Washington Capitals",
}


def _start(game: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(game["startTimeUTC"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, ValueError):
        return None


def _belongs(game: dict, team: str) -> bool:
    return any((game.get(side) or {}).get("abbrev") == team for side in ("homeTeam", "awayTeam"))


def parse_schedule(payload: dict, team: str, now: datetime | None = None) -> dict:
    """Pick a live game, a recently finished game, or the next game for one club."""
    if team not in TEAMS or not isinstance(payload, dict) or not isinstance(payload.get("games"), list):
        raise ValueError("invalid NHL schedule")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    games = [g for g in payload["games"] if isinstance(g, dict) and _belongs(g, team) and _start(g)]
    live = sorted((g for g in games if g.get("gameState") in ("LIVE", "CRIT")),
                  key=_start)
    recent = sorted((g for g in games if g.get("gameState") in ("OFF", "FINAL")
                     and _start(g) <= now and (now - _start(g)).total_seconds() < 12 * 3600),
                    key=_start, reverse=True)
    upcoming = sorted((g for g in games if g.get("gameState") in ("FUT", "PRE")
                       and _start(g) >= now), key=_start)
    game = next(iter(live or recent or upcoming), None)
    if game is None:
        return {"team": team, "state": "none"}
    state = "live" if game in live else "final" if game in recent else "upcoming"
    home, away = game.get("homeTeam") or {}, game.get("awayTeam") or {}
    period = game.get("periodDescriptor") or {}
    clock = game.get("clock") or {}
    result = {
        "team": team, "game_id": game.get("id"), "state": state, "home": home.get("abbrev", "---"),
        "away": away.get("abbrev", "---"), "start": _start(game).isoformat(),
        "home_score": home.get("score"), "away_score": away.get("score"),
        "period": period.get("number") or game.get("period"),
        "period_type": period.get("periodType", "REG"),
        "clock": clock.get("timeRemaining"),
    }
    return result
