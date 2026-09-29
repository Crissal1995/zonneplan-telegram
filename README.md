# ⚡ zonneplan-telegram

Fetches the hourly electricity prices from the [Zonneplan](https://www.zonneplan.nl) consumer API, sends a formatted price report plus a bar chart to Telegram, and archives the price history as one JSON file per day.

The user-facing messages are in Italian (`ct/kWh`, "Oggi"/"Domani").

## How it works

```mermaid
flowchart LR
    A["Zonneplan API<br/>consumer-prices/charts"] -->|hourly prices| B["bot.py<br/>main()"]
    B --> C["storage.py<br/>data/YYYY-MM-DD.json"]
    B --> D["chart.py<br/>chart.png"]
    B -->|Markdown summary| E["telegram/<br/>sendMessage"]
    B -->|PNG photo| F["telegram/<br/>sendPhoto"]
```

`main()` performs four steps:

1. **Fetch** — `get_zonneplan_hourly_prices()` calls `GET /api/consumer-prices/charts/electricity-hourly` and parses the payload into `APIResponse`.
2. **Archive** — `PriceStorage.save_prices()` groups the prices by local date and writes/updates `data/YYYY-MM-DD.json`.
3. **Notify** — `APIResponse.as_markdown()` renders the current tariff plus today's and tomorrow's min/max/average, which is sent with `sendMessage`.
4. **Chart** — `generate_zonneplan_bar_chart()` renders a Zonneplan-style bar chart (grey bars for hours already elapsed, green for the current hour and the future) and sends it with `sendPhoto`.

## Requirements

- Python >= 3.12 (CI runs 3.14)
- [uv](https://docs.astral.sh/uv/) for dependency management and execution
- A Telegram bot token and the target chat id

## Installation

```bash
git clone https://github.com/Crissal1995/zonneplan-telegram.git
cd zonneplan-telegram
uv sync
```

## Configuration

The credentials are read from the environment at runtime:

| Variable | Required | Description |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | yes | Bot token issued by [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | yes | Chat, group or channel id that receives the report |

For local development, create a `.env` file in the repository root — it is loaded automatically when `python-dotenv` is installed (it is part of the `dev` dependency group):

```dotenv
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=123456789
```

Both `send_telegram_message()` and `send_telegram_photo()` also accept explicit `bot_token` / `chat_id` arguments that take precedence over the environment.

## Usage

```bash
uv run zonneplan_telegram
```

The console script maps to `zonneplan_telegram.bot:main` (see `[project.scripts]` in `pyproject.toml`). Equivalent invocations:

```bash
uv run python -m zonneplan_telegram.bot
uv run -m zonneplan_telegram.bot   # uv's --module flag
```

Run `uv run -m zonneplan_telegram` (without `.bot`) only imports the package: the package has no `__main__.py`.

In CI the run is pinned and dev dependencies are excluded:

```bash
UV_FROZEN=1 UV_NO_DEV=1 uv run zonneplan_telegram
```

## Data storage

Price history is written to `data/`, relative to the current working directory, with one file per **local** day:

```json
{
  "2026-09-29T00:00:00+00:00": {
    "start_date": "2026-09-29T00:00:00+00:00",
    "end_date": "2026-09-29T01:00:00+00:00",
    "amount": 3360943.0
  }
}
```

- Keys are the UTC ISO-8601 start timestamps; the filename uses the local date.
- `amount` is the raw API value. `Price.price_eur` converts it with a `1e-7` factor and `Price.price_cents` with `1e-5`, so the example above is `33.61 ct/kWh`.
- An existing day file is only rewritten when the newly fetched data contains **more entries** than the stored file, so already-recorded hours are not overwritten.
- A missing file (or one that fails to parse) is treated as an empty history and reported through `loguru`; the run continues.

## Development

Quality gates are managed with [tox](https://tox.wiki) and the `tox-uv` plugin:

| Environment | Purpose | Commands |
| --- | --- | --- |
| `tox -e lint` | Linting | `ruff check` |
| `tox -e format` | Formatting check | `ruff format --check` |
| `tox -e type` | Type checking | `ty check` |
| `tox -e fix` | Auto-fixes | `ruff format`, `ruff check --fix`, `ty check --fix` |
| `tox` | All three checks | `lint`, `format`, `type` |

```bash
uv tool install tox --with tox-uv
tox          # run every qualification environment
tox -e fix   # apply automatic fixes
```

Ruff is configured with `line-length = 120` and `select = ["ALL"]`, ignoring copyright rules (`CPY`), the comma rule that conflicts with the formatter (`COM812`) and docstring rules (`D`).

### Continuous integration

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `qualify.yaml` | `pull_request` | Runs `tox` (lint, format check, type check) |
| `push.yaml` | `workflow_dispatch` | Runs the bot, then commits the new data through an auto-merged pull request |

`push.yaml` needs the `PAT` secret (a token with `repo` scope; the job already declares `contents: write` and `pull-requests: write`) and the two Telegram secrets. It runs the bot, closes any still-open pull request on the `automated-data-update` branch, opens a fresh one with `peter-evans/create-pull-request`, approves and squash-merges it with `--admin`. The approval and merge steps are skipped when no data changed and therefore no pull request was created.

## Project structure

```
.
├── .github/workflows/
│   ├── qualify.yaml              # PR quality gate (tox)
│   └── push.yaml                 # run the bot + auto-merge data updates
├── data/                         # archived price history (one JSON per day)
├── src/zonneplan_telegram/
│   ├── bot.py                    # entry point: fetch → archive → send
│   ├── chart.py                  # matplotlib bar chart
│   ├── storage.py                # per-day JSON persistence
│   ├── api/
│   │   ├── __init__.py           # API base URL
│   │   └── hourly_prices/
│   │       ├── __init__.py       # HTTP calls (hourly & quarter-hourly)
│   │       └── model.py          # pydantic models + Markdown rendering
│   └── telegram/
│       └── __init__.py           # sendMessage / sendPhoto clients
├── pyproject.toml                # metadata, deps, ruff & tox config
└── uv.lock
```

## API endpoints

Base URL: `https://app-api.zonneplan.nl/api`

- `GET /consumer-prices/charts/electricity-hourly` — used by the bot
- `GET /consumer-prices/charts/electricity-quarter-hourly` — available via `get_zonneplan_quarter_hourly_prices()`

## Notes

- `data/` and `chart.png` are resolved relative to the working directory, so run the bot from the repository root.
