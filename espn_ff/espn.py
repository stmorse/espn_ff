"""A thin wrapper around the ESPN fantasy football v3 read API.

Everything comes back as a pandas DataFrame.  When you need something this
class doesn't cover, use `League.raw()` and pick through the JSON yourself.
"""

import hashlib
import json
from pathlib import Path

import pandas as pd
import requests

from .config import REPO_ROOT
from .constants import (
    POSITION_CODES,
    PRO_TEAM_CODES,
    SLOT_CODES,
    STARTER_SLOTS,
    STAT_ACTUAL,
    STAT_PROJECTED,
    WINNER_AWAY,
    WINNER_HOME,
    WINNER_TIE,
    WINNER_UNDECIDED,
)

# ESPN moved the read API here in April 2024.  The old
# fantasy.espn.com/apis/v3 host still redirects, but not reliably.
BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

# Seasons before this are only reachable through the leagueHistory
# endpoint, which wraps its response in a list.
HISTORY_CUTOFF = 2018


class ESPNError(RuntimeError):
    pass


class League:
    """One league, one season.

    >>> league = League(league_id=572240, season=2025, **cfg.cookies)
    >>> league.teams()
    >>> league.schedule()
    >>> league.rosters(week=3)
    """

    def __init__(
        self,
        league_id: int,
        season: int,
        swid: str | None = None,
        espn_s2: str | None = None,
        cache: bool = True,
        cache_dir: str | Path | None = None,
    ):
        self.league_id = int(league_id)
        self.season = int(season)
        self.cookies = (
            {"SWID": swid, "espn_s2": espn_s2} if (swid and espn_s2) else {}
        )
        self.cache = cache
        self.cache_dir = Path(cache_dir or REPO_ROOT / ".cache")
        self._team_names: dict[int, str] | None = None

    # ------------------------------------------------------------------
    # fetching
    # ------------------------------------------------------------------

    def _cache_path(self, views, week) -> Path:
        key = json.dumps(
            [self.league_id, self.season, week, sorted(views)], sort_keys=True
        )
        digest = hashlib.md5(key.encode()).hexdigest()[:10]
        return self.cache_dir / f"{self.season}_{self.league_id}_{digest}.json"

    def raw(self, views, week: int | None = None, refresh: bool = False) -> dict:
        """Fetch raw JSON for one or more `view` parameters.

        Responses are cached on disk so you can iterate on analysis without
        re-hitting ESPN.  Pass refresh=True to force a new request.
        """
        if isinstance(views, str):
            views = [views]

        path = self._cache_path(views, week)
        if self.cache and not refresh and path.exists():
            return json.loads(path.read_text())

        if self.season < HISTORY_CUTOFF:
            url = f"{BASE_URL}/leagueHistory/{self.league_id}"
            params = {"view": list(views), "seasonId": self.season}
        else:
            url = f"{BASE_URL}/seasons/{self.season}/segments/0/leagues/{self.league_id}"
            params = {"view": list(views)}
        if week is not None:
            params["scoringPeriodId"] = week

        response = requests.get(url, params=params, cookies=self.cookies, timeout=30)

        if response.status_code == 401:
            raise ESPNError(
                "401 from ESPN -- this league is private and your cookies are "
                "missing or expired.  Refresh swid/espn_s2 in config.ini "
                "(see config.ini.example for where to find them)."
            )
        if response.status_code == 404:
            raise ESPNError(
                f"404 from ESPN -- no league {self.league_id} in season "
                f"{self.season}.  Check the league ID (it's in the URL when "
                f"you view your league) and that it existed that year."
            )
        response.raise_for_status()

        data = response.json()
        # leagueHistory returns a list of seasons; we asked for exactly one.
        if isinstance(data, list):
            if not data:
                raise ESPNError(f"ESPN returned no data for season {self.season}.")
            data = data[0]

        if self.cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))
        return data

    # ------------------------------------------------------------------
    # parsed views
    # ------------------------------------------------------------------

    def teams(self, refresh: bool = False) -> pd.DataFrame:
        """One row per team: name, record, points, and season-end ranks."""
        data = self.raw(["mTeam"], refresh=refresh)
        rows = []
        for team in data["teams"]:
            overall = team.get("record", {}).get("overall", {})
            rows.append(
                {
                    "team_id": team["id"],
                    "name": _team_name(team),
                    "abbrev": team.get("abbrev", ""),
                    "wins": overall.get("wins"),
                    "losses": overall.get("losses"),
                    "ties": overall.get("ties"),
                    "points_for": overall.get("pointsFor"),
                    "points_against": overall.get("pointsAgainst"),
                    "playoff_seed": team.get("playoffSeed"),
                    "draft_projected_rank": team.get("draftDayProjectedRank"),
                    "final_rank": team.get("rankCalculatedFinal"),
                }
            )
        return pd.DataFrame(rows).sort_values("team_id", ignore_index=True)

    def team_names(self, refresh: bool = False) -> dict[int, str]:
        """team_id -> display name."""
        if self._team_names is None or refresh:
            teams = self.teams(refresh=refresh)
            self._team_names = dict(zip(teams["team_id"], teams["name"]))
        return self._team_names

    def schedule(self, refresh: bool = False) -> pd.DataFrame:
        """One row per matchup for the whole season, scores included.

        `completed` is False for weeks that haven't been played yet, so
        filter on it before computing records.
        """
        data = self.raw(["mMatchup", "mMatchupScore"], refresh=refresh)
        names = self.team_names()
        rows = []
        for matchup in data["schedule"]:
            home, away = matchup.get("home"), matchup.get("away")
            # Leagues with an odd number of teams have bye matchups with
            # only one side; nothing to compare, so skip them.
            if not home or not away:
                continue
            winner = matchup.get("winner", WINNER_UNDECIDED)
            rows.append(
                {
                    "week": matchup["matchupPeriodId"],
                    "home_id": home["teamId"],
                    "home": names.get(home["teamId"], str(home["teamId"])),
                    "home_points": home.get("totalPoints"),
                    "away_id": away["teamId"],
                    "away": names.get(away["teamId"], str(away["teamId"])),
                    "away_points": away.get("totalPoints"),
                    "winner": winner,
                    "completed": winner != WINNER_UNDECIDED,
                    "playoff": matchup.get("playoffTierType", "NONE") != "NONE",
                }
            )
        return pd.DataFrame(rows).sort_values(
            ["week", "home_id"], ignore_index=True
        )

    def rosters(self, week: int, refresh: bool = False) -> pd.DataFrame:
        """Every rostered player for one week, with projected and actual points."""
        data = self.raw(["mMatchup", "mMatchupScore"], week=week, refresh=refresh)
        names = self.team_names()
        rows = []
        for team in data["teams"]:
            for entry in team.get("roster", {}).get("entries", []):
                player = entry["playerPoolEntry"]["player"]
                slot = entry["lineupSlotId"]

                projected = actual = None
                for stat in player.get("stats", []):
                    if stat.get("scoringPeriodId") != week:
                        continue
                    if stat.get("statSourceId") == STAT_ACTUAL:
                        actual = stat.get("appliedTotal")
                    elif stat.get("statSourceId") == STAT_PROJECTED:
                        projected = stat.get("appliedTotal")

                rows.append(
                    {
                        "week": week,
                        "team_id": team["id"],
                        "team": names.get(team["id"], str(team["id"])),
                        "player": player["fullName"],
                        "slot": slot,
                        "slot_name": SLOT_CODES.get(slot, str(slot)),
                        "started": slot in STARTER_SLOTS,
                        # Real position, not the slot they were played in --
                        # bench and flex players keep their true position.
                        "position": POSITION_CODES.get(
                            player.get("defaultPositionId"), "?"
                        ),
                        "pro_team": PRO_TEAM_CODES.get(player.get("proTeamId"), "?"),
                        # D/ST entries have no injuryStatus key at all.
                        "status": player.get("injuryStatus", "NA"),
                        "projected": projected,
                        "actual": actual,
                        # Which slots this player may legally fill --
                        # what makes an exact best-lineup solve possible.
                        "eligible_slots": tuple(player.get("eligibleSlots", ())),
                    }
                )
        return pd.DataFrame(rows)

    def lineup_slots(self, refresh: bool = False) -> dict[int, int]:
        """The league's starting lineup: slot id -> how many of them.

        Read from the league settings rather than hardcoded, so this
        works for superflex, two-QB, six-flex and other odd formats.
        Bench and IR are excluded -- they aren't starting slots.
        """
        data = self.raw(["mSettings"], refresh=refresh)
        counts = data["settings"]["rosterSettings"]["lineupSlotCounts"]
        return {
            int(slot): int(count)
            for slot, count in counts.items()
            if int(count) > 0 and int(slot) in STARTER_SLOTS
        }

    def rosters_range(self, weeks, refresh: bool = False) -> pd.DataFrame:
        """rosters() for several weeks, stacked.

        One request per week -- that's how the API is shaped -- but the
        cache means you only pay for it once.
        """
        frames = [self.rosters(week, refresh=refresh) for week in weeks]
        return pd.concat(frames, ignore_index=True)

    def last_completed_week(self) -> int:
        """Highest regular-season week with a result. 0 if none yet."""
        schedule = self.schedule()
        done = schedule.query("completed and not playoff")
        return int(done["week"].max()) if len(done) else 0


def _team_name(team: dict) -> str:
    """Team display name, handling both the old and new API shapes."""
    if team.get("name"):
        return " ".join(team["name"].split())
    parts = [team.get("location", ""), team.get("nickname", "")]
    name = " ".join(p for p in parts if p).strip()
    return name or f"Team {team['id']}"


# Re-exported so callers don't need to import constants for the common case.
__all__ = ["League", "ESPNError", "WINNER_HOME", "WINNER_AWAY", "WINNER_TIE"]
