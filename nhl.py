"""Small, defensive adapter for the NHL's public schedule feed."""

from __future__ import annotations

from datetime import datetime, timezone
import re

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

ROTATE_S = 10


def followed_teams(options: dict) -> list[str]:
    """An explicit list wins; old single-team screens keep their original team."""
    values = options.get("teams")
    if isinstance(values, list) and values:
        teams = list(dict.fromkeys(t for t in values if isinstance(t, str) and t in TEAMS))
        if teams:
            return teams
    team = options.get("team", "CGY")
    return [team if isinstance(team, str) and team in TEAMS else "CGY"]


def game_key(game: dict, team: str = "") -> tuple:
    game_id = game.get("game_id")
    if isinstance(game_id, (str, int)) and not isinstance(game_id, bool) and game_id:
        return ("id", game_id)
    return ("match", str(game.get("home") or team), str(game.get("away") or ""),
            str(game.get("start") or ""))


def games_for_teams(hockey: dict, teams: list[str], *, live_only=False) -> list[tuple[str, dict]]:
    """Keep each matchup once, favouring live games for regular screen rotation."""
    games, seen = [], set()
    for team in teams:
        game = hockey.get(team)
        if not isinstance(game, dict) or game.get("state") not in ("live", "final", "upcoming"):
            continue
        if live_only:
            age = game.get("age_s")
            if (game.get("state") != "live" or game.get("error")
                    or isinstance(age, (int, float)) and age > 90):
                continue
        key = game_key(game, team)
        if key not in seen:
            seen.add(key)
            games.append((team, game))
    if games and not live_only:
        rank = {"live": 0, "final": 1, "upcoming": 2}
        priority = min(rank[g["state"]] for _, g in games)
        games = [(team, g) for team, g in games if rank[g["state"]] == priority]
    return games


def _start(game: dict) -> datetime | None:
    try:
        value = datetime.fromisoformat(game["startTimeUTC"].replace("Z", "+00:00"))
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    except (KeyError, AttributeError, ValueError):
        return None


def _belongs(game: dict, team: str) -> bool:
    return any(_object(game.get(side)).get("abbrev") == team for side in ("homeTeam", "awayTeam"))


def _object(value):
    return value if isinstance(value, dict) else {}


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 999 else None


def _clock_seconds(clock):
    value = clock.get("secondsRemaining")
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 7200:
        return value
    text = clock.get("timeRemaining")
    if isinstance(text, str) and re.fullmatch(r"\d{1,2}:[0-5]\d", text):
        minutes, seconds = map(int, text.split(":"))
        return minutes * 60 + seconds
    return None


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
    home, away = _object(game.get("homeTeam")), _object(game.get("awayTeam"))
    period = _object(game.get("periodDescriptor"))
    clock = _object(game.get("clock"))
    seconds = _clock_seconds(clock)
    result = {
        "team": team, "game_id": game.get("id"), "state": state, "home": home.get("abbrev", "---"),
        "away": away.get("abbrev", "---"), "start": _start(game).isoformat(),
        "home_score": _count(home.get("score")), "away_score": _count(away.get("score")),
        "home_shots": _count(home.get("sog")), "away_shots": _count(away.get("sog")),
        "period": period.get("number") or game.get("period"),
        "period_type": period.get("periodType", "REG"),
        "clock": f"{seconds // 60:02}:{seconds % 60:02}" if seconds is not None else None,
        "clock_seconds": seconds, "clock_running": clock.get("running") is True,
        "intermission": clock.get("inIntermission") is True,
        "clock_observed_at": now.isoformat(),
    }
    return result


def parse_game_detail(payload: dict, selected: dict, now: datetime | None = None) -> dict:
    """Enrich the selected game with authoritative live clock/shot fields."""
    if not isinstance(payload, dict) or payload.get("id") != selected.get("game_id"):
        raise ValueError("NHL game ID mismatch")
    for side in ("home", "away"):
        if _object(payload.get(side + "Team")).get("abbrev") != selected.get(side):
            raise ValueError("NHL game teams mismatch")
    detail = parse_schedule({"games": [payload]}, selected["team"], now)
    if detail.get("game_id") != selected.get("game_id"):
        raise ValueError("NHL game detail unavailable")
    return detail


def poll_interval(game: dict, now: datetime) -> int:
    if game.get("state") == "live":
        return 15
    if game.get("state") == "upcoming":
        start = _start({"startTimeUTC": game.get("start")})
        if start and 0 <= (start - now).total_seconds() < 7200:
            return 60
    return 300


def game_status(game: dict, now: datetime) -> str:
    """Use real break flags; extrapolate only a fresh, running period clock."""
    kind, number = game.get("period_type"), game.get("period")
    if game.get("state") == "final":
        return "FINAL/" + kind if kind in ("OT", "SO") else "FINAL"
    if game.get("error") or (isinstance(game.get("age_s"), (int, float)) and game["age_s"] > 90):
        return "STALE"
    if game.get("intermission"):
        if kind == "OT":
            return "OT INT"
        return {1: "1ST INT", 2: "2ND INT", 3: "3RD INT"}.get(number, "INT")
    if kind == "SO":
        return "SHOOTOUT"
    period = "OT" if kind == "OT" else f"P{number}" if _count(number) else "LIVE"
    seconds = game.get("clock_seconds")
    if not isinstance(seconds, int) or isinstance(seconds, bool):
        seconds = _clock_seconds({"timeRemaining": game.get("clock")})
    if seconds is None:
        return period
    if game.get("clock_running") is True:
        observed = _start({"startTimeUTC": game.get("clock_observed_at")})
        if observed:
            age = max(0, (now - observed).total_seconds())
            if age > 30:
                return period + " SYNC"
            seconds = max(0, seconds - int(age))
    return f"{period} {seconds // 60:02}:{seconds % 60:02}"
