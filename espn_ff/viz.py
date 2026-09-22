"""Shared chart styling so every script in this repo looks like the others.

Two themes, each picked for its own background rather than flipped from the
other.  Call `use_theme()` first, and it hands back the palette to draw with.
"""

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

from .config import REPO_ROOT

THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "ink_secondary": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "accent": "#2a78d6",
        # A second series color, for a fit line over accent-colored points.
        "fit": "#eb6834",
        # Diverging poles: one cool, one warm, neutral gray between them.
        "diverging": ("#2a78d6", "#f0efec", "#d03b3b"),
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#ffffff",
        "ink_secondary": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "accent": "#3987e5",
        "fit": "#d95926",
        "diverging": ("#3987e5", "#383835", "#e66767"),
    },
}


def use_theme(theme: str = "light") -> dict:
    """Apply the theme to matplotlib and return its palette."""
    if theme not in THEMES:
        raise ValueError(f"Unknown theme {theme!r}; pick one of {list(THEMES)}")
    palette = THEMES[theme]
    mpl.rcParams.update(
        {
            "figure.facecolor": palette["surface"],
            "axes.facecolor": palette["surface"],
            "savefig.facecolor": palette["surface"],
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
            "text.color": palette["ink"],
            "axes.labelcolor": palette["ink_secondary"],
            "axes.edgecolor": palette["axis"],
            "axes.linewidth": 0.8,
            "axes.titlesize": 15,
            "axes.labelsize": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.color": palette["muted"],
            "ytick.color": palette["muted"],
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            # Hairline solid grid, one shade off the surface -- never dashed.
            "grid.color": palette["grid"],
            "grid.linewidth": 0.8,
            "grid.linestyle": "-",
            "figure.dpi": 110,
            "savefig.dpi": 200,
            "savefig.bbox": "tight",
        }
    )
    return palette


def diverging_cmap(palette: dict) -> LinearSegmentedColormap:
    """Two-pole colormap built from the theme's diverging colors."""
    return LinearSegmentedColormap.from_list("luck", palette["diverging"], N=256)


def centered_norm(values, center: float = 0.0) -> TwoSlopeNorm:
    """A norm that keeps `center` at the neutral midpoint of the colormap."""
    values = np.asarray(values, dtype=float)
    reach = max(float(np.abs(values - center).max()), 1e-6)
    return TwoSlopeNorm(vmin=center - reach, vcenter=center, vmax=center + reach)


def repel_labels(
    ax,
    xs,
    ys,
    labels,
    pad=0.02,
    fontsize=10,
    color=None,
    leader_threshold=6.0,
    max_iter=120,
):
    """Label every point without letting the labels collide.

    Each label starts beside its point, on whichever side of the plot
    leaves more room.  Then overlaps are resolved against the labels'
    real rendered extents, nudging them vertically until nothing
    collides.  Labels that end up far from their point get a leader line.

    This is the part that would otherwise be a dict of hand-tuned offsets.
    """
    xs, ys = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)
    fig = ax.figure
    color = color or mpl.rcParams["text.color"]

    x_lo, x_hi = ax.get_xlim()
    x_pad = (x_hi - x_lo) * pad
    midpoint = (x_lo + x_hi) / 2

    texts = []
    for x, y, label in zip(xs, ys, labels):
        on_right = x < midpoint
        texts.append(
            ax.text(
                x + (x_pad if on_right else -x_pad), y, label,
                ha="left" if on_right else "right", va="center",
                fontsize=fontsize, color=color, zorder=5,
            )
        )

    # Resolve against rendered extents, so this works for any label length.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    to_data = ax.transData.inverted()
    y_bounds = sorted(ax.transData.transform([(x_lo, v) for v in ax.get_ylim()])[:, 1])

    for _ in range(max_iter):
        boxes = [t.get_window_extent(renderer=renderer).expanded(1.0, 1.25)
                 for t in texts]
        shifts = np.zeros(len(texts))
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                a, b = boxes[i], boxes[j]
                if a.xmax <= b.xmin or b.xmax <= a.xmin:
                    continue  # no horizontal overlap, so they cannot collide
                overlap = min(a.ymax, b.ymax) - max(a.ymin, b.ymin)
                if overlap <= 0:
                    continue
                # Push the lower box down and the upper box up, evenly.
                push = overlap / 2 + 0.5
                if a.y0 < b.y0:
                    shifts[i] -= push
                    shifts[j] += push
                else:
                    shifts[i] += push
                    shifts[j] -= push

        if not shifts.any():
            break

        for text, shift in zip(texts, shifts):
            if not shift:
                continue
            px, py = ax.transData.transform(text.get_position())
            py = float(np.clip(py + shift, y_bounds[0], y_bounds[1]))
            text.set_position(to_data.transform((px, py)))

    # Leader lines for labels that had to travel to find room.
    for text, x, y in zip(texts, xs, ys):
        label_y = text.get_position()[1]
        moved = abs(ax.transData.transform((x, label_y))[1]
                    - ax.transData.transform((x, y))[1])
        if moved < leader_threshold:
            continue
        anchor = text.get_position()[0]
        ax.plot([x, anchor], [y, label_y], linewidth=0.7, zorder=2,
                color=mpl.rcParams["grid.color"], solid_capstyle="round")

    return texts


def save(fig, filename, output_dir=None) -> Path:
    """Write the figure under output/ and return where it landed."""
    output_dir = Path(output_dir or REPO_ROOT / "output")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    fig.savefig(path)
    return path


def show():
    plt.show()
