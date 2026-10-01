"""
Zonneplan-style bar chart rendered as SVG.

The chart is built from strings only, so the serverless bundle stays small and
``/chart`` does not pay for importing matplotlib (and numpy) on a cold start.

Hours are labelled, and split into past and upcoming, in the price market timezone
(``MARKET_TIMEZONE``) rather than in the timezone of the machine that renders the SVG,
so the axis stays correct when the chart is generated on a UTC server such as Vercel.
"""

from __future__ import annotations

import datetime
import math
from pathlib import Path
from typing import TYPE_CHECKING

from zonneplan_telegram.api.hourly_prices.model import MARKET_TIMEZONE

if TYPE_CHECKING:
    from zonneplan_telegram.api.hourly_prices.model import Prices

# Canvas geometry, in SVG user units (1 unit == 1 px at the declared width).
WIDTH = 1200
HEIGHT = 620
MARGIN_LEFT = 78
MARGIN_RIGHT = 28
MARGIN_TOP = 32
MARGIN_BOTTOM = 58

# Bar heights are scaled from 0 up to the next multiple of Y_TICK_STEP, expanded a little
# so the value label of the tallest bar still fits between the bar and the top of the plot.
Y_TICK_STEP = 5
Y_HEADROOM_RATIO = 1.06
X_LABEL_HOUR_INTERVAL = 3
X_LABEL_OFFSET = 26
Y_LABEL_OFFSET = 12
Y_TITLE_OFFSET = 26
BAR_WIDTH_RATIO = 0.72
BAR_CORNER_RADIUS = 8
EXTREME_LABEL_OFFSET = 10

FONT_FAMILY = "Helvetica, Arial, sans-serif"
TEXT_COLOR = "#666666"
EXTREME_TEXT_COLOR = "#333333"
GRID_COLOR = "#cccccc"
BAR_COLOR_PAST = "#d0d0d0"
BAR_COLOR_ACTIVE = "#4caf50"
Y_AXIS_TITLE = "ct / kWh"

CANVAS_ATTRIBUTES = f'width="{WIDTH}" height="{HEIGHT}"'
CANVAS_VIEW_BOX = f'viewBox="0 0 {WIDTH} {HEIGHT}"'
LABEL_STYLE = f'font-family="{FONT_FAMILY}" font-size="15" fill="{TEXT_COLOR}"'
X_LABEL_STYLE = f'{LABEL_STYLE} text-anchor="middle"'
Y_LABEL_STYLE = f'{LABEL_STYLE} text-anchor="end" dominant-baseline="middle"'
EXTREME_LABEL_STYLE = (
    f'font-family="{FONT_FAMILY}" font-size="15" fill="{EXTREME_TEXT_COLOR}" text-anchor="middle" font-weight="bold"'
)


def generate_zonneplan_bar_chart(prices: Prices, output_path: str = "chart.svg") -> Path:
    """
    Renders ``prices`` as a Zonneplan-style bar chart and returns the path it wrote.

    A bar is grey once its hour has completely elapsed, and green for the hour in
    progress and every hour after it, mirroring the Zonneplan app.
    """
    if not prices:
        msg = "Cannot render a chart without prices."
        raise ValueError(msg)

    output_file = Path(output_path)
    output_file.write_text(_render_svg(prices), encoding="utf-8")
    return output_file


def _render_svg(prices: Prices) -> str:
    plot_width = WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    plot_height = HEIGHT - MARGIN_TOP - MARGIN_BOTTOM
    axis_max = _axis_max(max(item.price_cents for item in prices))

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" {CANVAS_ATTRIBUTES} {CANVAS_VIEW_BOX}>',
        f'<rect {CANVAS_ATTRIBUTES} fill="#ffffff"/>',
        *_grid(plot_height, axis_max),
        *_bars(prices, plot_width, plot_height, axis_max),
        *_hour_labels(prices, plot_width, plot_height),
        *_extreme_labels(prices, plot_width, plot_height, axis_max),
        _y_axis_title(plot_height),
        "</svg>",
    ]
    return "\n".join(elements)


def _axis_max(highest: float) -> float:
    """Rounds the highest price up to a multiple of the tick step, leaving room for its value label."""
    if highest <= 0:
        return float(Y_TICK_STEP)
    return math.ceil(highest * Y_HEADROOM_RATIO / Y_TICK_STEP) * Y_TICK_STEP


def _y_position(value: float, plot_height: float, axis_max: float) -> float:
    return MARGIN_TOP + plot_height * (1 - value / axis_max)


def _grid(plot_height: float, axis_max: float) -> list[str]:
    """Horizontal gridlines with their value labels."""
    right = WIDTH - MARGIN_RIGHT
    elements = []

    for value in range(0, int(axis_max) + Y_TICK_STEP, Y_TICK_STEP):
        y = _n(_y_position(value, plot_height, axis_max))
        elements.append(f'<line x1="{MARGIN_LEFT}" y1="{y}" x2="{right}" y2="{y}" stroke="{GRID_COLOR}"/>')
        elements.append(f'<text x="{MARGIN_LEFT - Y_LABEL_OFFSET}" y="{y}" {Y_LABEL_STYLE}>{value}</text>')

    return elements


def _bars(prices: Prices, plot_width: float, plot_height: float, axis_max: float) -> list[str]:
    now = datetime.datetime.now(MARKET_TIMEZONE)
    slot = plot_width / len(prices)
    width = slot * BAR_WIDTH_RATIO

    elements = []
    for index, item in enumerate(prices):
        height = plot_height * item.price_cents / axis_max
        center = MARGIN_LEFT + slot * (index + 0.5)
        top = MARGIN_TOP + plot_height - height
        color = BAR_COLOR_PAST if item.end_date.astimezone(MARKET_TIMEZONE) <= now else BAR_COLOR_ACTIVE
        bar = _bar_path(center - width / 2, top, width, height)
        elements.append(f'<path d="{bar}" fill="{color}"/>')

    return elements


def _bar_path(x: float, y: float, width: float, height: float) -> str:
    """A bar whose top corners are rounded, so the chart reads softer than plain rectangles."""
    radius = min(BAR_CORNER_RADIUS, width / 2, height)
    bottom = y + height
    return (
        f"M {_n(x)} {_n(bottom)}"
        f" V {_n(y + radius)}"
        f" Q {_n(x)} {_n(y)} {_n(x + radius)} {_n(y)}"
        f" H {_n(x + width - radius)}"
        f" Q {_n(x + width)} {_n(y)} {_n(x + width)} {_n(y + radius)}"
        f" V {_n(bottom)} Z"
    )


def _extreme_labels(prices: Prices, plot_width: float, plot_height: float, axis_max: float) -> list[str]:
    """Writes the value on top of the cheapest and the most expensive bar."""
    slot = plot_width / len(prices)
    cheapest = min(range(len(prices)), key=lambda index: prices[index].price_cents)
    most_expensive = max(range(len(prices)), key=lambda index: prices[index].price_cents)

    elements = []
    for index in sorted({cheapest, most_expensive}):
        height = plot_height * prices[index].price_cents / axis_max
        center = _n(MARGIN_LEFT + slot * (index + 0.5))
        baseline = _n(MARGIN_TOP + plot_height - height - EXTREME_LABEL_OFFSET)
        elements.append(
            f'<text x="{center}" y="{baseline}" {EXTREME_LABEL_STYLE}>{prices[index].price_cents:.2f}</text>'
        )

    return elements


def _hour_labels(prices: Prices, plot_width: float, plot_height: float) -> list[str]:
    """Hour labels every ``X_LABEL_HOUR_INTERVAL`` hours, in the price market timezone."""
    slot = plot_width / len(prices)
    baseline = _n(MARGIN_TOP + plot_height + X_LABEL_OFFSET)

    elements = []
    for index, item in enumerate(prices):
        start_local = item.start_date.astimezone(MARKET_TIMEZONE)
        if start_local.hour % X_LABEL_HOUR_INTERVAL != 0:
            continue
        center = _n(MARGIN_LEFT + slot * (index + 0.5))
        elements.append(f'<text x="{center}" y="{baseline}" {X_LABEL_STYLE}>{start_local:%H}</text>')

    return elements


def _y_axis_title(plot_height: float) -> str:
    transform = f"translate({Y_TITLE_OFFSET} {_n(MARGIN_TOP + plot_height / 2)}) rotate(-90)"
    return f'<text transform="{transform}" {X_LABEL_STYLE}>{Y_AXIS_TITLE}</text>'


def _n(value: float) -> str:
    """Formats a coordinate without trailing zeros, to keep the SVG compact."""
    return f"{value:.2f}".rstrip("0").rstrip(".")
