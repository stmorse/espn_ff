"""Real standings vs. "what if everyone played everyone" standings.

Each week, instead of scoring your team against the one opponent the
schedule handed you, score it against the whole league.  Teams above the
diagonal have been unlucky -- they score well and lose anyway.  Teams below
it have been carried by their schedule.

    python scripts/luck_chart.py
    python scripts/luck_chart.py --week 9 --league-id 84667 --theme dark

Importable too, if you'd rather work in a notebook:

    from espn_ff import League, analysis
    from scripts.luck_chart import make_chart
    table = analysis.records(League(84667, 2025).schedule(), through_week=9)
    fig = make_chart(table, week=9)
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from espn_ff import League, analysis, config, viz  # noqa: E402


def make_chart(records, week, league_name=None, theme="light"):
    """Scatter of real win% against all-play win%.  Returns the figure."""
    palette = viz.use_theme(theme)
    fig, ax = plt.subplots(figsize=(8.5, 8.5))

    real = records["win_pct"].to_numpy()
    all_play = records["all_play_pct"].to_numpy()
    luck = records["luck"].to_numpy()

    # Square limits around the data, so the diagonal sits at a true 45
    # degrees and "above the line" reads correctly.  Padded generously
    # to leave room for the team labels.
    lo = min(real.min(), all_play.min())
    hi = max(real.max(), all_play.max())
    margin = max((hi - lo) * 0.28, 0.08)
    lo, hi = max(lo - margin, -0.02), min(hi + margin, 1.02)
    ax.set(xlim=(lo, hi), ylim=(lo, hi))
    ax.set_aspect("equal")

    # Reference line: on it, your record matches your scoring.  Dashed
    # because it is a threshold, not a gridline.
    ax.plot([lo, hi], [lo, hi], linestyle="--", linewidth=1.2,
            color=palette["axis"], zorder=1)

    points = ax.scatter(
        real, all_play,
        s=200,
        c=luck,
        cmap=viz.diverging_cmap(palette),
        norm=viz.centered_norm(luck),
        edgecolors=palette["surface"],   # 2px surface ring, not a border
        linewidths=2,
        zorder=3,
    )

    ticks = [t / 100 for t in range(0, 101, 10) if lo <= t / 100 <= hi]
    ax.set_xticks(ticks)
    ax.set_yticks(ticks)
    ax.set_xticklabels([f"{t:.0%}" for t in ticks])
    ax.set_yticklabels([f"{t:.0%}" for t in ticks])
    ax.grid(True, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)

    ax.set_xlabel("Actual win %")
    ax.set_ylabel("Win % if you played every team, every week")

    # Name the two corners so the chart explains itself.
    lucky, unlucky = palette["diverging"][2], palette["diverging"][0]
    ax.text(0.985, 0.015, "LUCKY", transform=ax.transAxes, color=lucky,
            fontsize=12, style="italic", ha="right", va="bottom", zorder=2)
    ax.text(0.015, 0.985, "UNLUCKY", transform=ax.transAxes, color=unlucky,
            fontsize=12, style="italic", ha="left", va="top", zorder=2)

    viz.repel_labels(ax, real, all_play, list(records["name"]),
                     color=palette["ink_secondary"])

    # Title and subtitle are offset in points, not axes fractions --
    # set_aspect("equal") changes the axes height, and a fractional
    # offset would slide the subtitle into the title.
    title = "Who's actually good, and who's just lucky"
    subtitle = f"Through week {week}"
    if league_name:
        subtitle = f"{league_name}  \u00b7  {subtitle}"
    for text, dy, size, weight, shade in (
        (subtitle, 10, 10.5, "normal", palette["muted"]),
        (title, 28, 15, "bold", palette["ink"]),
    ):
        ax.annotate(text, xy=(0, 1), xycoords="axes fraction",
                    xytext=(0, dy), textcoords="offset points",
                    ha="left", va="bottom", fontsize=size,
                    fontweight=weight, color=shade)

    # Scale legend for the color ramp, tucked into the empty corner
    # rather than given a full-width bar of its own.
    cax = ax.inset_axes([0.03, 0.07, 0.30, 0.02])
    bar = fig.colorbar(points, cax=cax, orientation="horizontal")
    bar.outline.set_visible(False)
    bar.ax.tick_params(length=0, labelsize=8.5, colors=palette["muted"], pad=3)
    reach = float(np.abs(luck).max())
    bar.set_ticks([-reach, reach])
    bar.set_ticklabels([f"-{reach:.0%}", f"+{reach:.0%}"])
    cax.set_title("wins vs. what your scores earned",
                  fontsize=8.5, color=palette["muted"], pad=5)

    fig.tight_layout()
    return fig


def main():
    cfg = config.load()
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--league-id", type=int, default=cfg.league_id)
    parser.add_argument("--season", type=int, default=cfg.season)
    parser.add_argument("--week", type=int, default=None,
                        help="through this week (default: last completed)")
    parser.add_argument("--theme", choices=["light", "dark"], default="light")
    parser.add_argument("--out", default=None, help="output filename")
    parser.add_argument("--refresh", action="store_true",
                        help="bypass the cache and re-fetch from ESPN")
    parser.add_argument("--show", action="store_true",
                        help="open a window instead of only saving")
    args = parser.parse_args()

    if not args.league_id:
        parser.error("no league id -- pass --league-id or set it in config.ini")

    league = League(args.league_id, args.season,
                    swid=cfg.swid, espn_s2=cfg.espn_s2)
    schedule = league.schedule(refresh=args.refresh)

    week = args.week or league.last_completed_week()
    if not week:
        parser.error(f"no completed weeks yet in the {args.season} season")

    records = analysis.records(schedule, through_week=week)
    fig = make_chart(records, week, theme=args.theme)

    filename = args.out or f"luck_{args.league_id}_{args.season}_wk{week}.png"
    path = viz.save(fig, filename)
    print(records[["name", "wins", "losses", "win_pct",
                   "all_play_pct", "luck"]].to_string(index=False))
    print(f"\nSaved {path}")

    if args.show:
        viz.show()


if __name__ == "__main__":
    main()
