"""
Zonneplan-style bar chart rendered as SVG.

The chart is built from strings only, so the serverless bundle stays small and
``/chart`` does not pay for importing matplotlib (and numpy) on a cold start.
"""

from __future__ import annotations

import datetime
import math
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zonneplan_telegram.api.hourly_prices.model import Prices

# Canvas geometry, in SVG user units (1 unit == 1 px at the declared width).
WIDTH = 1200
HEIGHT = 620
MARGIN_LEFT = 78
MARGIN_RIGHT = 28
MARGIN_TOP = 32
MARGIN_BOTTOM = 58

# Bar heights are scaled from 0 up to the next multiple of Y_TICK_STEP.
Y_TICK_STEP = 5
X_LABEL_HOUR_INTERVAL = 3
X_LABEL_OFFSET = 26
Y_LABEL_OFFSET = 12
Y_TITLE_OFFSET = 26
BAR_WIDTH_RATIO = 0.72

FONT_FAMILY = "Helvetica, Arial, sans-serif"
TEXT_COLOR = "#666666"
GRID_COLOR = "#cccccc"
BAR_COLOR_PAST = "#d0d0d0"
BAR_COLOR_ACTIVE = "#4caf50"
Y_AXIS_TITLE = "ct / kWh"

CANVAS_ATTRIBUTES = f'width="{WIDTH}" height="{HEIGHT}"'
CANVAS_VIEW_BOX = f'viewBox="0 0 {WIDTH} {HEIGHT}"'
LABEL_STYLE = f'font-family="{FONT_FAMILY}" font-size="15" fill="{TEXT_COLOR}"'
X_LABEL_STYLE = f'{LABEL_STYLE} text-anchor="middle"'
Y_LABEL_STYLE = f'{LABEL_STYLE} text-anchor="end" dominant-baseline="middle"'


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
        _y_axis_title(plot_height),
        "</svg>",
    ]
    return "\n".join(elements)


def _axis_max(highest: float) -> float:
    """Rounds the highest price up to a multiple of the tick step."""
    if highest <= 0:
        return float(Y_TICK_STEP)
    return math.ceil(highest / Y_TICK_STEP) * Y_TICK_STEP


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
    now_local = datetime.datetime.now().astimezone()
    slot = plot_width / len(prices)
    width = slot * BAR_WIDTH_RATIO

    elements = []
    for index, item in enumerate(prices):
        height = plot_height * item.price_cents / axis_max
        x = MARGIN_LEFT + slot * index + (slot - width) / 2
        y = MARGIN_TOP + plot_height - height
        color = BAR_COLOR_PAST if item.end_date.astimezone() <= now_local else BAR_COLOR_ACTIVE
        elements.append(f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(width)}" height="{_n(height)}" fill="{color}"/>')

    return elements


def _hour_labels(prices: Prices, plot_width: float, plot_height: float) -> list[str]:
    """Hour labels every ``X_LABEL_HOUR_INTERVAL`` hours, in local time."""
    slot = plot_width / len(prices)
    baseline = _n(MARGIN_TOP + plot_height + X_LABEL_OFFSET)

    elements = []
    for index, item in enumerate(prices):
        start_local = item.start_date.astimezone()
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
