"""How good are ESPN's weekly projections, position by position?

Each dot is one rostered player in one week: projected points across,
what they actually scored up the side.  A perfect projection would put
every dot on the dashed diagonal.  The solid line is the actual fit --
where it's flatter than the diagonal, the projections are too confident,
calling for more spread than really happens.

    python scripts/proj_vs_actual.py
    python scripts/proj_vs_actual.py --start-week 1 --end-week 6
    python scripts/proj_vs_actual.py --positions QB RB --started-only

Importable too:

    from espn_ff import League, analysis
    from scripts.proj_vs_actual import make_chart
    rosters = League(84667, 2025).rosters_range(range(1, 10))
    fig = make_chart(rosters, weeks=range(1, 10))
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from espn_ff import League, analysis, config, viz  # noqa: E402


def make_chart(rosters, weeks, positions=None, started_only=False,
               league_name=None, theme="light"):
    """Small multiples of projected vs. actual, one facet per position."""
    palette = viz.use_theme(theme)
    positions = list(positions or analysis.SKILL_POSITIONS)

    points = analysis.projection_error(
        rosters, positions=positions, started_only=started_only,
        min_projected=0.0,
    )
    if points.empty:
        raise ValueError("No projected/actual pairs to plot in that range.")

    stats = analysis.projection_accuracy(
        rosters, positions=positions, started_only=started_only,
    ).set_index("position")

    # Keep only positions that actually have data, in a stable order.
    positions = [p for p in positions if p in set(points["position"])]

    ncols = 2 if len(positions) > 2 else len(positions)
    nrows = int(np.ceil(len(positions) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.6 * ncols, 4.7 * nrows))
    axes = np.atleast_1d(axes).ravel()

    # Each facet gets its own square scale.  A shared one across
    # positions would squash TEs into a corner to make room for QBs,
    # and the comparison that matters here is each position against the
    # diagonal, not against the other positions' point totals.
    for ax, position in zip(axes, positions):
        group = points[points["position"] == position]
        projected = group["projected"].to_numpy(dtype=float)
        actual = group["actual"].to_numpy(dtype=float)

        # Square limits, so the diagonal sits at a true 45 degrees.
        lo = min(projected.min(), actual.min())
        hi = max(projected.max(), actual.max())
        margin = (hi - lo) * 0.07
        lo, hi = lo - margin, hi + margin
        ax.set(xlim=(lo, hi), ylim=(lo, hi))
        ax.set_aspect("equal")
        ax.grid(True, linewidth=0.8, zorder=0)
        ax.set_axisbelow(True)

        # Perfect projection: dashed, because it's a reference, not a grid.
        ax.plot([lo, hi], [lo, hi], linestyle="--", linewidth=1.1,
                color=palette["axis"], zorder=1)

        ax.scatter(projected, actual, s=26, alpha=0.38, linewidths=0,
                   color=palette["accent"], zorder=2)

        # Least-squares fit, drawn only across the range with data.
        row = stats.loc[position]
        if np.isfinite(row["slope"]):
            slope, intercept = np.polyfit(projected, actual, 1)
            span = np.array([projected.min(), projected.max()])
            ax.plot(span, slope * span + intercept, linewidth=2,
                    color=palette["fit"], zorder=3)

        ax.set_title(position, loc="left", fontsize=13, fontweight="bold",
                     color=palette["ink"], pad=8)

        bias = row["bias"]
        if abs(bias) < 0.25:
            bias_line = "no systematic bias"
        else:
            bias_line = (f"projects {abs(bias):.1f} pts too "
                         f"{'low' if bias > 0 else 'high'}")
        caption = (
            f"$r^2$ = {row['r2']:.2f}\n"
            f"{bias_line}\n"
            f"n = {int(row['n']):,}"
        )
        # Bottom-right: the corner scatter never fills, since it would
        # mean big projections that scored nothing.
        ax.text(0.96, 0.04, caption, transform=ax.transAxes, va="bottom",
                ha="right", fontsize=9.5, linespacing=1.5,
                color=palette["ink_secondary"], zorder=4)

    for ax in axes[len(positions):]:
        ax.set_visible(False)

    # Label the outer edges only, so the facets stay uncluttered.
    for index, ax in enumerate(axes[:len(positions)]):
        if index % ncols == 0:
            ax.set_ylabel("Actual points")
        if index >= len(positions) - ncols:
            ax.set_xlabel("Projected points")

    weeks = list(weeks)
    week_label = (
        f"week {weeks[0]}" if len(weeks) == 1
        else f"weeks {weeks[0]}–{weeks[-1]}"
    )
    scope = "starters only" if started_only else "all rostered players"
    subtitle = f"{week_label}  ·  {scope}"
    if league_name:
        subtitle = f"{league_name}  ·  {subtitle}"

    fig.tight_layout(rect=(0, 0.035, 1, 0.9))

    # Placed after tight_layout and measured from the top of the figure,
    # so the subtitle can't ride up into the title.
    fig.text(0.02, 0.985, "How much should you trust the projections?",
             ha="left", va="top", fontsize=16, fontweight="bold",
             color=palette["ink"])
    fig.text(0.02, 0.945, subtitle, ha="left", va="top", fontsize=10.5,
             color=palette["muted"])
    fig.text(0.02, 0.012,
             "Dashed line = a perfect projection.   Solid line = the actual fit.",
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
    parser.add_argument("--positions", nargs="+",
                        default=list(analysis.SKILL_POSITIONS),
                        help="e.g. QB RB WR TE K D/ST")
    parser.add_argument("--started-only", action="store_true",
                        help="only players who were in a starting slot")
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
    print(f"Fetching weeks {args.start_week}-{end_week} "
          f"({len(weeks)} request{'s' if len(weeks) > 1 else ''}, cached after the first run)...")
    rosters = league.rosters_range(weeks, refresh=args.refresh)

    fig = make_chart(rosters, weeks, positions=args.positions,
                     started_only=args.started_only, theme=args.theme)

    filename = args.out or (
        f"projections_{args.league_id}_{args.season}"
        f"_wk{args.start_week}-{end_week}.png"
    )
    path = viz.save(fig, filename)

    stats = analysis.projection_accuracy(
        rosters, positions=args.positions, started_only=args.started_only)
    print()
    print(stats.round(3).to_string(index=False))
    print(f"\nSaved {path}")

    if args.show:
        viz.show()


if __name__ == "__main__":
    main()
