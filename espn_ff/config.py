"""Load credentials and defaults from config.ini (or the environment)."""

import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = REPO_ROOT / "config.ini"


@dataclass
class Config:
    swid: str | None = None
    espn_s2: str | None = None
    league_id: int | None = None
    season: int | None = None
    cache_dir: Path = field(default_factory=lambda: REPO_ROOT / ".cache")
    output_dir: Path = field(default_factory=lambda: REPO_ROOT / "output")

    @property
    def cookies(self) -> dict:
        """Cookie dict for requests; empty if no credentials (public leagues)."""
        if self.swid and self.espn_s2:
            return {"SWID": self.swid, "espn_s2": self.espn_s2}
        return {}


def _clean(value: str | None) -> str | None:
    """Strip whitespace and any quotes a user pasted along with the value."""
    if value is None:
        return None
    value = value.strip().strip('"').strip("'")
    return value or None


def load(path: str | Path | None = None) -> Config:
    """Read config.ini, letting ESPN_* environment variables win.

    Missing file is fine -- you can pass everything on the command line.
    """
    path = Path(path) if path else DEFAULT_PATH
    section = {}
    if path.exists():
        # ESPN cookie values contain '%' escapes; stop configparser
        # from trying to interpolate them.
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(path)
        if parser.has_section("espn"):
            section = dict(parser["espn"])

    swid = _clean(os.environ.get("ESPN_SWID") or section.get("swid"))
    espn_s2 = _clean(os.environ.get("ESPN_S2") or section.get("espn_s2"))
    league_id = _clean(os.environ.get("ESPN_LEAGUE_ID") or section.get("league_id"))
    season = _clean(os.environ.get("ESPN_SEASON") or section.get("season"))

    # SWID is expected in braces; add them back if the user stripped them.
    if swid and not swid.startswith("{"):
        swid = "{" + swid + "}"

    return Config(
        swid=swid,
        espn_s2=espn_s2,
        league_id=int(league_id) if league_id else None,
        season=int(season) if season else None,
    )
