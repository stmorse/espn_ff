"""What you scored, what ESPN told you to score, and what you could have scored.

Three numbers per team:

  actual    what the lineup you set really scored
  ESPN      what you'd have scored starting ESPN's projected best lineup
  best      the most your roster could possibly have scored

The gap between actual and best is what you left on the bench. Nobody
closes it -- "best" is pure hindsight -- but the size of the gap, and
how much of it ESPN's advice would have picked up, is the interesting
part. Teams are ranked worst-to-best, so the manager who left the most
points sitting is on top.

    python scripts/lineup_efficiency.py
    python scripts/lineup_efficiency.py --start-week 1 --end-week 6 --theme dark

Importable too:

    from espn_ff import League, analysis
    from scripts.lineup_efficiency import make_chart
    league = League(84667, 2025)
    weekly = analysis.lineup_efficiency(
        league.rosters_range(range(1, 10)), league.lineup_slots())
    fig = make_chart(analysis.season_efficiency(weekly), weeks=range(1, 10))
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from espn_ff import League, analysis, config, viz  # noqa: E402


def make_chart(season, weeks, league_name=None, theme="light"):
    """Ranked dumbbell of actual vs. ESPN vs. best-possible.  Returns the figure."""
    palette = viz.use_theme(theme)
    season = season.reset_index(drop=True)

    # Everything is measured as a deficit from that team's own ceiling,
    # so every row starts at the same origin.  Plotting raw point totals
    # instead scatters the rows by how strong each roster was, and the
    # gaps -- the thing the chart is about -- stop being comparable.
    order = season.iloc[::-1].reset_index(drop=True)   # worst manager on top
    y = np.arange(len(order))
    actual_gap = (order["optimal"] - order["actual"]).to_numpy()
    espn_gap = (order["optimal"] - order["espn"]).to_numpy()

    height = max(3.4, 0.52 * len(order) + 2.6)
    fig, ax = plt.subplots(figsize=(10.5, height))

    reach = max(actual_gap.max(), espn_gap.max())
    for row, a, e in zip(y, actual_gap, espn_gap):
        ax.plot([0, max(a, e)], [row, row], linewidth=1, zorder=1,
                color=palette["grid"], solid_capstyle="round")
        # The bar the eye should read: how far short of the ceiling
        # this manager's real lineup landed.
        ax.plot([0, a], [row, row], linewidth=4.5, alpha=0.3, zorder=2,
                color=palette["accent"], solid_capstyle="round")

    ax.scatter(espn_gap, y, s=70, marker="D", color=palette["fit"],
               edgecolors=palette["surface"], linewidths=1.5, zorder=4)
    ax.scatter(actual_gap, y, s=115, marker="o", color=palette["accent"],
               edgecolors=palette["surface"], linewidths=1.5, zorder=5)

    # The number belongs beside the blue dot it describes, not beside
    # whichever mark happens to sit furthest right -- flip it to the
    # other side of the dot when the diamond is in the way.
    for row, a, e in zip(y, actual_gap, espn_gap):
        crowded = 0 <= (e - a) < reach * 0.1
        ax.text(a + reach * 0.025 * (-1 if crowded else 1), row, f"{a:,.0f}",
                va="center", ha="right" if crowded else "left",
                fontsize=10, color=palette["ink_secondary"])

    # The ceiling is the origin now, so it's a rule rather than a mark.
    ax.axvline(0, color=palette["ink_secondary"], linewidth=1.2, zorder=3)

    ax.set_yticks(y)
    ax.set_yticklabels(order["team"], fontsize=10.5)
    ax.tick_params(axis="y", length=0)
    ax.set_ylim(-0.8, len(order) - 0.2)
    ax.set_xlim(-reach * 0.04, reach * 1.16)
    ax.set_xlabel("Points short of your roster's ceiling")
    ax.grid(True, axis="x", linewidth=0.8, zorder=0)
    ax.grid(False, axis="y")
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)

    marks = [
        Line2D([], [], marker="o", linestyle="", markersize=10,
               color=palette["accent"], markeredgecolor=palette["surface"],
               label="The lineup you set"),
        Line2D([], [], marker="D", linestyle="", markersize=8,
               color=palette["fit"], markeredgecolor=palette["surface"],
               label="ESPN's projected best lineup"),
        Line2D([], [], linestyle="-", linewidth=1.2,
               color=palette["ink_secondary"],
               label="The best your roster could have done"),
    ]
    ax.legend(handles=marks, loc="lower left", bbox_to_anchor=(0, 1.005),
              ncol=3, frameon=False, handletextpad=0.5, columnspacing=1.8,
              fontsize=9.5, labelcolor=palette["ink_secondary"])

    fig.tight_layout(rect=(0, 0.045, 1, 0.9))

    weeks = list(weeks)
    week_label = (f"week {weeks[0]}" if len(weeks) == 1
                  else f"weeks {weeks[0]}–{weeks[-1]}")
    total_left = season["left_on_bench"].sum()
    beat_espn = int((season["vs_espn"] > 0).sum())
    subtitle = (f"{week_label}  ·  {total_left:,.0f} points left on benches "
                f"league-wide")
    if league_name:
        subtitle = f"{league_name}  ·  {subtitle}"

    fig.text(0.012, 0.985, "Points left on the bench", ha="left", va="top",
             fontsize=16, fontweight="bold", color=palette["ink"])
    fig.text(0.012, 0.945, subtitle, ha="left", va="top", fontsize=10.5,
             color=palette["muted"])
    fig.text(0.012, 0.012,
             f"Shorter is better -- every team is measured against its own "
             f"ceiling, not against each other.   "
             f"{beat_espn} of {len(season)} teams beat ESPN's recommended lineup.",
             ha="left", va="bottom", fontsize=9, color=palette["muted"])
    return fig


def main():
    cfg = config.load()
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--league-id", type=int, default=cfg.league_id)
    parser.add_argument("--season", type=int, default=cfg.season)
    parser.add_argument("--start-week", type=int, default=1)
    parser.add_argument("--end-week", type=int, default=None,
                        help="default: last completed week")
    parser.add_argument("--theme", choices=["light", "dark"], default="light")
    parser.add_argument("--out", default=None)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    if not args.league_id:
        parser.error("no league id -- pass --league-id or set it in config.ini")

    league = League(args.league_id, args.season,
                    swid=cfg.swid, espn_s2=cfg.espn_s2)

    end_week = args.end_week or league.last_completed_week()
    if not end_week:
        parser.error(f"no completed weeks yet in the {args.season} season")
    if end_week < args.start_week:
        parser.error(f"--end-week {end_week} is before --start-week {args.start_week}")

    weeks = range(args.start_week, end_week + 1)
    slots = league.lineup_slots(refresh=args.refresh)
    print("Starting lineup:", ", ".join(
        f"{analysis.slot_label(slot)}x{count}" for slot, count in sorted(slots.items())))
    print(f"Fetching weeks {args.start_week}-{end_week} "
          f"({len(weeks)} request{'s' if len(weeks) > 1 else ''}, "
          f"cached after the first run)...")

    rosters = league.rosters_range(weeks, refresh=args.refresh)
    weekly = analysis.lineup_efficiency(rosters, slots)
    season = analysis.season_efficiency(weekly)

    fig = make_chart(season, weeks, theme=args.theme)
    filename = args.out or (
        f"lineups_{args.league_id}_{args.season}"
        f"_wk{args.start_week}-{end_week}.png"
    )
    path = viz.save(fig, filename)

    shown = season[["team", "actual", "espn", "optimal",
                    "left_on_bench", "vs_espn", "captured"]].copy()
    shown["captured"] = (shown["captured"] * 100).round(1)
    print()
    print(shown.round(1).to_string(index=False))
    print(f"\nSaved {path}")

    if args.show:
        viz.show()


if __name__ == "__main__":
    main()
