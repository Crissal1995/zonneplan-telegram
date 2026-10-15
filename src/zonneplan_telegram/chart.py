"""
Zonneplan-style bar chart rendered as a JPEG.

The chart is drawn with Pillow on a raster canvas because Telegram renders raster images
inline through ``sendPhoto``, whereas an SVG only arrives as a downloadable file. Hours are
labelled, and split into past and upcoming, in the price market timezone (``MARKET_TIMEZONE``)
rather than in the timezone of the machine that renders the image, so the axis stays correct
when the chart is generated on a UTC server such as Vercel.
"""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, cast

from PIL import Image, ImageDraw, ImageFont

from zonneplan_telegram.api.hourly_prices.model import MARKET_TIMEZONE

if TYPE_CHECKING:
    from PIL.ImageFont import FreeTypeFont

    from zonneplan_telegram.api.hourly_prices.model import Prices

# Canvas geometry, in pixels.
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
FONT_SIZE = 15
JPEG_QUALITY = 90

BACKGROUND_COLOR = "#ffffff"
TEXT_COLOR = "#666666"
EXTREME_TEXT_COLOR = "#333333"
GRID_COLOR = "#cccccc"
BAR_COLOR_PAST = "#d0d0d0"
BAR_COLOR_ACTIVE = "#4caf50"
Y_AXIS_TITLE = "ct / kWh"


class _Plot(NamedTuple):
    """Geometry shared by the drawing helpers."""

    width: float
    height: float
    axis_max: float


def generate_zonneplan_bar_chart(prices: Prices, output_path: str = "chart.jpg") -> Path:
    """
    Renders ``prices`` as a Zonneplan-style bar chart and returns the path it wrote.

    A bar is grey once its hour has completely elapsed, and green for the hour in
    progress and every hour after it, mirroring the Zonneplan app.
    """
    if not prices:
        msg = "Cannot render a chart without prices."
        raise ValueError(msg)

    output_file = Path(output_path)
    _render_image(prices).save(output_file, format="JPEG", quality=JPEG_QUALITY)
    return output_file


def _render_image(prices: Prices) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(image)
    font = _load_font(FONT_SIZE)
    plot = _Plot(
        width=WIDTH - MARGIN_LEFT - MARGIN_RIGHT,
        height=HEIGHT - MARGIN_TOP - MARGIN_BOTTOM,
        axis_max=_axis_max(max(item.price_cents for item in prices)),
    )

    _draw_grid(draw, font, plot)
    _draw_bars(draw, prices, plot)
    _draw_hour_labels(draw, font, prices, plot)
    _draw_extreme_labels(draw, font, prices, plot)
    _draw_y_axis_title(image, font, plot)
    return image


def _load_font(size: int) -> FreeTypeFont:
    """Returns a scalable font, using Pillow's bundled default so no system font is required."""
    return cast("FreeTypeFont", ImageFont.load_default(size=size))


def _axis_max(highest: float) -> float:
    """Rounds the highest price up to a multiple of the tick step, leaving room for its value label."""
    if highest <= 0:
        return float(Y_TICK_STEP)
    return math.ceil(highest * Y_HEADROOM_RATIO / Y_TICK_STEP) * Y_TICK_STEP


def _y_position(value: float, plot_height: float, axis_max: float) -> float:
    return MARGIN_TOP + plot_height * (1 - value / axis_max)


def _draw_grid(draw: ImageDraw.ImageDraw, font: FreeTypeFont, plot: _Plot) -> None:
    """Horizontal gridlines with their value labels."""
    right = WIDTH - MARGIN_RIGHT

    for value in range(0, int(plot.axis_max) + Y_TICK_STEP, Y_TICK_STEP):
        y = _y_position(value, plot.height, plot.axis_max)
        draw.line(((MARGIN_LEFT, y), (right, y)), fill=GRID_COLOR, width=1)
        draw.text((MARGIN_LEFT - Y_LABEL_OFFSET, y), str(value), font=font, fill=TEXT_COLOR, anchor="rm")


def _draw_bars(draw: ImageDraw.ImageDraw, prices: Prices, plot: _Plot) -> None:
    now = dt.datetime.now(MARKET_TIMEZONE)
    slot = plot.width / len(prices)
    width = slot * BAR_WIDTH_RATIO
    baseline = MARGIN_TOP + plot.height

    for index, item in enumerate(prices):
        height = plot.height * item.price_cents / plot.axis_max
        center = MARGIN_LEFT + slot * (index + 0.5)
        color = BAR_COLOR_PAST if item.end_date.astimezone(MARKET_TIMEZONE) <= now else BAR_COLOR_ACTIVE
        box = (round(center - width / 2), round(baseline - height), round(center + width / 2), round(baseline))
        _draw_bar(draw, box, color)


def _draw_bar(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], color: str) -> None:
    """A bar whose top corners are rounded, so the chart reads softer than plain rectangles."""
    left, top, right, bottom = box
    radius = min(BAR_CORNER_RADIUS, (right - left) / 2, (bottom - top) / 2)
    draw.rectangle((left, top + round(radius), right, bottom), fill=color)
    draw.rounded_rectangle((left, top, right, top + round(2 * radius)), radius=radius, fill=color)


def _draw_extreme_labels(draw: ImageDraw.ImageDraw, font: FreeTypeFont, prices: Prices, plot: _Plot) -> None:
    """Writes the value on top of the cheapest and the most expensive bar."""
    slot = plot.width / len(prices)
    cheapest = min(range(len(prices)), key=lambda index: prices[index].price_cents)
    most_expensive = max(range(len(prices)), key=lambda index: prices[index].price_cents)
    baseline = MARGIN_TOP + plot.height

    for index in sorted({cheapest, most_expensive}):
        height = plot.height * prices[index].price_cents / plot.axis_max
        center = MARGIN_LEFT + slot * (index + 0.5)
        draw.text(
            (center, baseline - height - EXTREME_LABEL_OFFSET),
            f"{prices[index].price_cents:.2f}",
            font=font,
            fill=EXTREME_TEXT_COLOR,
            anchor="ms",
        )


def _draw_hour_labels(draw: ImageDraw.ImageDraw, font: FreeTypeFont, prices: Prices, plot: _Plot) -> None:
    """Hour labels every ``X_LABEL_HOUR_INTERVAL`` hours, in the price market timezone."""
    slot = plot.width / len(prices)
    y = MARGIN_TOP + plot.height + X_LABEL_OFFSET

    for index, item in enumerate(prices):
        start_local = item.start_date.astimezone(MARKET_TIMEZONE)
        if start_local.hour % X_LABEL_HOUR_INTERVAL != 0:
            continue
        center = MARGIN_LEFT + slot * (index + 0.5)
        draw.text((center, y), f"{start_local:%H}", font=font, fill=TEXT_COLOR, anchor="ma")


def _draw_y_axis_title(image: Image.Image, font: FreeTypeFont, plot: _Plot) -> None:
    """Draws the ``ct / kWh`` unit rotated along the left gutter."""
    left, top, right, bottom = font.getbbox(Y_AXIS_TITLE)
    tile = Image.new("RGBA", (int(right - left) + 4, int(bottom - top) + 8), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((2 - left, 4 - top), Y_AXIS_TITLE, font=font, fill=TEXT_COLOR)
    rotated = tile.rotate(90, expand=True)
    center_y = MARGIN_TOP + plot.height / 2
    image.paste(rotated, (Y_TITLE_OFFSET - rotated.width // 2, round(center_y - rotated.height / 2)), rotated)
