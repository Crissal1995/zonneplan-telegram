# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project

`zonneplan-telegram` fetches the hourly electricity prices from the Zonneplan consumer API, answers Telegram commands through a webhook, and archives the price history as one JSON file per day.

- **Webhook** — `app.py` → `src/zonneplan_telegram/vercel.py` (FastAPI, `POST /api/webhook`). Answers `/priceNow`, `/priceTomorrow`, `/chart` and `/help` on demand.
- **Scheduled CLI** — `src/zonneplan_telegram/bot.py` (`main()`). Fetches, archives to `data/` and sends the full report; run by the `push.yaml` GitHub Action, never by the webhook.

Python >= 3.12, managed with [uv](https://docs.astral.sh/uv/).

## Commands

```bash
uv sync                     # install / refresh dependencies (uv.lock)
uv run zonneplan_telegram   # run the scheduled CLI from the repo root
uv run set-webhook <url>    # register the Telegram webhook (… --info, --delete)

uv tool install tox --with tox-uv
tox                         # run every quality gate
tox -e fix                  # apply automatic fixes
```

Quality gates (also enforced by CI, **run before finishing any change**):

```bash
uv run ruff check
uv run ruff format --check
uv run ty check
```

## Architecture

```
app.py                          # Vercel entrypoint: prepends src/ to sys.path, re-exports app
src/zonneplan_telegram/
  bot.py                        # scheduled CLI: fetch → archive → send
  vercel.py                     # FastAPI webhook application
  commands.py                   # command handlers + Telegram menu metadata
  chart.py                      # pure-stdlib SVG bar chart
  storage.py                    # per-day JSON persistence
  api/hourly_prices/            # HTTP calls + pydantic models + Markdown rendering
  telegram/                     # sendMessage / sendDocument clients, allowlist, models, set-webhook CLI
data/                           # archived price history, one JSON file per local day
```

Two entrypoints share the same modules: the webhook (`vercel.py`) and the scheduled CLI (`bot.py`).

## Conventions

- **English everywhere** — code, comments, docstrings, README and every Telegram-facing message / button label. Do not introduce Italian strings.
- Ruff is configured with `select = ["ALL"]`, `line-length = 120`, ignoring `CPY`, `COM812` and `D`. Keep new code clean without adding blanket `# noqa`.
- Recurring lint patterns:
  - `msg = "..."` then `raise ValueError(msg)` (EM101/TRY003).
  - Type-only imports go in `if TYPE_CHECKING:` (TC001/TC003), but FastAPI request models must stay runtime imports (`# noqa: TC001`).
  - FastAPI route params need `Annotated[...]` dependencies (FAST002).
  - Lazy function-level imports need `# noqa: PLC0415`.
  - Implicit string concatenation inside a collection must be parenthesized (ISC004); prefer single lines that fit in 120 chars.
- Runtime dependencies stay minimal (`fastapi`, `loguru`, `pydantic`, `requests`). Do not add matplotlib/numpy — `chart.py` assembles the SVG from plain strings.

## Gotchas

- **Vercel entrypoint** — `[tool.vercel] entrypoint = "app:app"` points at the root `app.py` shim. Vercel resolves it as a module path relative to the repo root, so it *cannot* reference `zonneplan_telegram.vercel:app` directly for this `src` layout. `app.py` prepends `src/` to `sys.path` (hence `# noqa: E402`). Keep the `vercel.json` `functions` key in sync with `app.py`.
- **Filesystem** — Vercel is read-only except `/tmp`; `/chart` writes its SVG there. Only the GitHub Action (`bot.py`) writes to `data/`.
- **Charts** — Telegram rejects SVG in `sendPhoto`, so charts are delivered with `sendDocument` (`send_telegram_document`). A bar is `#d0d0d0` only once its whole hour has elapsed, otherwise `#4caf50`.
- **Storage** — an existing day file is only rewritten when the new data has *more* entries, so recorded hours are never overwritten. `data/` and `chart.svg` resolve relative to the working directory, so run the CLI from the repo root.
- **Allowlist** — an empty allowlist denies everyone; `TELEGRAM_CHAT_ID` or `TELEGRAM_ALLOWED_CHAT_IDS` must be set for commands to work.
- **Dependencies** — Vercel and CI build with uv; run `uv sync` after editing deps so `uv.lock` stays in sync.

## Configuration

Read from the environment at runtime (local `.env` is loaded when `python-dotenv` is installed):

| Variable | Required | Description |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | yes | Bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | yes | Chat that receives the scheduled report; default allowlist |
| `TELEGRAM_ALLOWED_CHAT_IDS` | no | Comma-separated chat ids the webhook may answer |
| `TELEGRAM_WEBHOOK_SECRET` | recommended | Echoed by Telegram in `X-Telegram-Bot-Api-Secret-Token` |

## Reference

See `README.md` for the full command table, deployment steps, data-storage format and CI details.
