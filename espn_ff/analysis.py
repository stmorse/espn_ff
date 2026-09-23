"""League-level calculations that don't belong to any one chart."""

import numpy as np
import pandas as pd

from .constants import SLOT_CODES, WINNER_AWAY, WINNER_HOME, WINNER_TIE


def team_games(schedule: pd.DataFrame, team_id: int) -> pd.DataFrame:
    """One team's games, always from that team's point of view.

    Returns columns week / points / opponent_id / opponent_points / result,
    which is usually what you want instead of wrangling home vs away.
    """
    home = schedule.query("home_id == @team_id").rename(
        columns={
            "home_points": "points",
            "away_id": "opponent_id",
            "away": "opponent",
            "away_points": "opponent_points",
        }
    )
    home["result"] = np.where(
        home["winner"] == WINNER_HOME, "W",
        np.where(home["winner"] == WINNER_TIE, "T", "L"),
    )
    away = schedule.query("away_id == @team_id").rename(
        columns={
            "away_points": "points",
            "home_id": "opponent_id",
            "home": "opponent",
            "home_points": "opponent_points",
        }
    )
    away["result"] = np.where(
        away["winner"] == WINNER_AWAY, "W",
        np.where(away["winner"] == WINNER_TIE, "T", "L"),
    )

    cols = ["week", "points", "opponent_id", "opponent", "opponent_points",
            "result", "completed", "playoff"]
    return (
        pd.concat([home[cols], away[cols]])
        .sort_values("week", ignore_index=True)
    )


def weekly_scores(schedule: pd.DataFrame) -> pd.DataFrame:
    """Flatten the schedule to one row per team per week: week / team_id / points."""
    home = schedule[["week", "home_id", "home", "home_points"]].rename(
        columns={"home_id": "team_id", "home": "name", "home_points": "points"}
    )
    away = schedule[["week", "away_id", "away", "away_points"]].rename(
        columns={"away_id": "team_id", "away": "name", "away_points": "points"}
    )
    return pd.concat([home, away]).sort_values(
        ["week", "team_id"], ignore_index=True
    )


def records(
    schedule: pd.DataFrame,
    through_week: int | None = None,
    include_playoffs: bool = False,
) -> pd.DataFrame:
    """Real record vs. the record every team would have played everyone.

    The all-play record asks: each week, how would this team have done
    against the *whole league* rather than the one opponent the schedule
    handed it?  The gap between the two is schedule luck.

    Ties count as half a win on both sides.
    """
    games = schedule.query("completed")
    if not include_playoffs:
        games = games.query("not playoff")
    if through_week is not None:
        games = games.query("week <= @through_week")
    if games.empty:
        raise ValueError(
            "No completed games in that range -- has the season started?"
        )

    # --- real record, straight off ESPN's own winner field ---
    real = {}
    for _, game in games.iterrows():
        for team_id, name, outcome in (
            (game["home_id"], game["home"], game["winner"]),
            (game["away_id"], game["away"], game["winner"]),
        ):
            row = real.setdefault(
                team_id, {"name": name, "w": 0, "l": 0, "t": 0}
            )
            if outcome == WINNER_TIE:
                row["t"] += 1
            elif (outcome == WINNER_HOME) == (team_id == game["home_id"]):
                row["w"] += 1
            else:
                row["l"] += 1

    # --- all-play record: compare each score to every other score that week ---
    scores = weekly_scores(games)
    allplay = {team_id: {"w": 0, "l": 0, "t": 0} for team_id in real}
    for _, week in scores.groupby("week"):
        points = dict(zip(week["team_id"], week["points"]))
        for team_id, own in points.items():
            if team_id not in allplay:
                continue
            others = [p for other, p in points.items() if other != team_id]
            allplay[team_id]["w"] += sum(own > p for p in others)
            allplay[team_id]["l"] += sum(own < p for p in others)
            allplay[team_id]["t"] += sum(own == p for p in others)

    points_for = scores.groupby("team_id")["points"].sum()

    rows = []
    for team_id, row in real.items():
        ap = allplay[team_id]
        rows.append(
            {
                "team_id": team_id,
                "name": row["name"],
                "wins": row["w"],
                "losses": row["l"],
                "ties": row["t"],
                "win_pct": _pct(row["w"], row["l"], row["t"]),
                "all_play_wins": ap["w"],
                "all_play_losses": ap["l"],
                "all_play_ties": ap["t"],
                "all_play_pct": _pct(ap["w"], ap["l"], ap["t"]),
                "points_for": points_for.get(team_id, 0.0),
            }
        )

    table = pd.DataFrame(rows)
    # Positive luck = won more than the scores alone say you should have.
    table["luck"] = table["win_pct"] - table["all_play_pct"]
    return table.sort_values(
        ["win_pct", "points_for"], ascending=False, ignore_index=True
    )


def _pct(wins: int, losses: int, ties: int) -> float:
    total = wins + losses + ties
    return (wins + 0.5 * ties) / total if total else 0.0


# Positions worth charting by default.  K and D/ST are projected so
# loosely that they mostly just compress the axes.
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")


def projection_error(
    rosters: pd.DataFrame,
    positions=SKILL_POSITIONS,
    started_only: bool = False,
    min_projected: float = 0.0,
) -> pd.DataFrame:
    """Rows usable for a projected-vs-actual comparison.

    Drops players with no projection, no result, or a projection at or
    below `min_projected` (byes and inactives, mostly).  Adds `error`,
    which is positive when a player beat their projection.
    """
    table = rosters.dropna(subset=["projected", "actual"]).copy()
    table = table[table["projected"] > min_projected]
    if started_only:
        table = table[table["started"]]
    if positions:
        table = table[table["position"].isin(positions)]
    table["error"] = table["actual"] - table["projected"]
    return table.reset_index(drop=True)


def projection_accuracy(rosters: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """How well ESPN projected each position.

    r2      -- how much of the variation in actual points the projection
               explains.  1.0 is perfect, 0.0 is no better than guessing
               the average.
    bias    -- mean(actual - projected).  Negative means ESPN projects
               this position too high.
    mae     -- mean absolute error, in fantasy points.
    slope   -- fit of actual on projected.  Below 1 means the projections
               are too spread out: they over-predict the high end and
               under-predict the low end.
    """
    table = projection_error(rosters, **kwargs)
    rows = []
    for position, group in table.groupby("position", sort=False):
        projected = group["projected"].to_numpy(dtype=float)
        actual = group["actual"].to_numpy(dtype=float)
        rows.append(
            {
                "position": position,
                "n": len(group),
                "r2": _r_squared(projected, actual),
                "bias": float(np.mean(actual - projected)),
                "mae": float(np.mean(np.abs(actual - projected))),
                "slope": _slope(projected, actual),
                "mean_projected": float(np.mean(projected)),
                "mean_actual": float(np.mean(actual)),
            }
        )
    order = {p: i for i, p in enumerate(SKILL_POSITIONS)}
    return (
        pd.DataFrame(rows)
        .sort_values("position", key=lambda c: c.map(lambda p: order.get(p, 99)))
        .reset_index(drop=True)
    )


def _r_squared(x, y) -> float:
    """Squared Pearson correlation.  NaN when there's nothing to correlate."""
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1] ** 2)


def _slope(x, y) -> float:
    if len(x) < 2 or np.std(x) == 0:
        return float("nan")
    return float(np.polyfit(x, y, 1)[0])


# --------------------------------------------------------------------
# Lineup efficiency: what you scored, what ESPN's advice would have
# scored, and the best you could have done knowing the results.
# --------------------------------------------------------------------

INELIGIBLE = -1e6


def best_lineup(players: pd.DataFrame, slot_counts: dict, rank_by: str):
    """Pick the highest-scoring legal lineup, ranking players by `rank_by`.

    This is an assignment problem -- each starting slot takes one player,
    each player fills at most one slot, and players are only eligible for
    certain slots -- so it's solved exactly rather than greedily.  Greedy
    position-by-position filling gets the common QB/RB/WR/TE/FLEX case
    right but quietly breaks on superflex and multi-flex leagues.

    Returns (chosen_rows, total_actual_points).  Ranking by "actual"
    gives the best possible lineup in hindsight; ranking by "projected"
    gives the lineup ESPN's projections recommended.
    """
    from scipy.optimize import linear_sum_assignment

    slots = [slot for slot, count in sorted(slot_counts.items())
             for _ in range(count)]
    if players.empty or not slots:
        return players.iloc[:0], 0.0

    scores = players[rank_by].fillna(0).to_numpy(dtype=float)
    eligible = players["eligible_slots"].tolist()

    value = np.full((len(players), len(slots)), INELIGIBLE)
    for i, slots_for_player in enumerate(eligible):
        for j, slot in enumerate(slots):
            if slot in slots_for_player:
                value[i, j] = scores[i]

    rows, cols = linear_sum_assignment(value, maximize=True)
    # Drop any pairing the solver only made because it had to fill a
    # slot no eligible player was left for.
    keep = [r for r, c in zip(rows, cols) if value[r, c] > INELIGIBLE]
    chosen = players.iloc[keep]
    return chosen, float(chosen["actual"].fillna(0).sum())


def lineup_efficiency(
    rosters: pd.DataFrame,
    slot_counts: dict,
    through_week: int | None = None,
) -> pd.DataFrame:
    """Per team per week: actual, ESPN-recommended, and best-possible points.

    actual   -- what the manager's lineup really scored
    espn     -- what they'd have scored starting ESPN's projected best
    optimal  -- the most their roster could have scored that week

    `optimal` is hindsight, so nobody should expect to hit it; the point
    is the gap, and how much of that gap ESPN's advice would have closed.
    """
    table = rosters.copy()
    if through_week is not None:
        table = table[table["week"] <= through_week]
    if table.empty:
        raise ValueError("No roster data in that range.")
    if "eligible_slots" not in table.columns:
        raise ValueError(
            "rosters is missing 'eligible_slots' -- re-fetch with "
            "League.rosters(); cached data from an older version won't have it."
        )

    rows = []
    for (week, team_id), players in table.groupby(["week", "team_id"]):
        actual = float(
            players.loc[players["started"], "actual"].fillna(0).sum()
        )
        _, espn = best_lineup(players, slot_counts, "projected")
        _, optimal = best_lineup(players, slot_counts, "actual")
        rows.append(
            {
                "week": week,
                "team_id": team_id,
                "team": players["team"].iloc[0],
                "actual": actual,
                "espn": espn,
                "optimal": optimal,
                "left_on_bench": optimal - actual,
                "vs_espn": actual - espn,
            }
        )
    return pd.DataFrame(rows).sort_values(["week", "team_id"], ignore_index=True)


def season_efficiency(weekly: pd.DataFrame) -> pd.DataFrame:
    """Sum `lineup_efficiency` over weeks, one row per team.

    `captured` is the share of the roster's possible points the manager
    actually got -- comparable across teams in a way raw points aren't.
    """
    table = (
        weekly.groupby(["team_id", "team"], as_index=False)[
            ["actual", "espn", "optimal"]
        ]
        .sum()
    )
    table["weeks"] = weekly.groupby(["team_id", "team"], as_index=False)[
        "week"
    ].count()["week"]
    table["left_on_bench"] = table["optimal"] - table["actual"]
    table["vs_espn"] = table["actual"] - table["espn"]
    table["captured"] = np.where(
        table["optimal"] > 0, table["actual"] / table["optimal"], np.nan
    )
    table["espn_captured"] = np.where(
        table["optimal"] > 0, table["espn"] / table["optimal"], np.nan
    )
    return table.sort_values("left_on_bench", ascending=False, ignore_index=True)


def slot_label(slot_id: int) -> str:
    """Human-readable name for a lineup slot id."""
    return SLOT_CODES.get(slot_id, str(slot_id))
