# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project

`zonneplan-telegram` fetches the hourly electricity prices from the Zonneplan consumer API, answers Telegram commands through a webhook, and archives the price history as one JSON file per day.

- **Webhook** — `app.py` → `src/zonneplan_telegram/vercel.py` (FastAPI, `POST /api/webhook`). Answers `/priceNow`, `/priceTomorrow`, `/chart`, `/digest`, `/subscribe`, `/unsubscribe` and `/help` on demand.
- **Scheduled CLI** — `src/zonneplan_telegram/cli.py` (`update_prices()`). Fetches the prices and archives them to `data/`; run by the `push.yaml` GitHub Action, never by the webhook.
- **Daily digest** — subscribers (`UPSTASH_REDIS_REST_URL`/`_TOKEN`) get a daily message at `DIGEST_HOUR` (06:00 `Europe/Amsterdam`); an external scheduler pings `GET|POST /api/digest` with the `X-Digest-Secret` header.

Python >= 3.12, managed with [uv](https://docs.astral.sh/uv/).

## Commands

```bash
uv sync                     # install / refresh dependencies (uv.lock)
uv run update-prices        # run the scheduled CLI from the repo root
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
  cli.py                        # scheduled CLI: fetch → archive
  vercel.py                     # FastAPI webhook application + digest trigger
  commands.py                   # command handlers + Telegram menu metadata
  digest.py                     # daily digest rendering + subscriber fan-out
  subscriptions.py              # Upstash Redis subscriber store (digest)
  chart.py                      # Pillow JPEG bar chart
  storage.py                    # per-day JSON persistence
  api/hourly_prices/            # HTTP calls + pydantic models + Markdown rendering
  telegram/                     # sendMessage / sendPhoto clients, allowlist, models, set-webhook CLI
data/                           # archived price history, one JSON file per local day
```

Two entrypoints share the same modules: the webhook (`vercel.py`) and the scheduled CLI (`cli.py`).

## Conventions

- **English everywhere** — code, comments, docstrings, README and every Telegram-facing message / button label. Do not introduce Italian strings.
- Ruff is configured with `select = ["ALL"]`, `line-length = 120`, ignoring `CPY`, `COM812` and `D`. Keep new code clean without adding blanket `# noqa`.
- Recurring lint patterns:
  - `msg = "..."` then `raise ValueError(msg)` (EM101/TRY003).
  - Type-only imports go in `if TYPE_CHECKING:` (TC001/TC003), but FastAPI request models must stay runtime imports (`# noqa: TC001`).
  - FastAPI route params need `Annotated[...]` dependencies (FAST002).
  - Lazy function-level imports need `# noqa: PLC0415`.
  - Implicit string concatenation inside a collection must be parenthesized (ISC004); prefer single lines that fit in 120 chars.
- Runtime dependencies stay minimal (`fastapi`, `loguru`, `pillow`, `pydantic`, `requests`, `tzdata`). Do not add matplotlib/numpy — `chart.py` draws the JPEG with Pillow. `tzdata` backs `MARKET_TIMEZONE`; without it `zoneinfo` cannot resolve `Europe/Amsterdam` on platforms that ship no system tz database, such as Windows.

## Gotchas

- **Vercel entrypoint** — `[tool.vercel] entrypoint = "app:app"` points at the root `app.py` shim. Vercel resolves it as a module path relative to the repo root, so it *cannot* reference `zonneplan_telegram.vercel:app` directly for this `src` layout. `app.py` prepends `src/` to `sys.path` (hence `# noqa: E402`). Keep the `vercel.json` `functions` key in sync with `app.py`.
- **Filesystem** — Vercel is read-only except `/tmp`; `/chart` writes its JPEG there. Only the GitHub Action (`cli.py`) writes to `data/`.
- **Chart hours** — every hour is resolved in `MARKET_TIMEZONE` (`Europe/Amsterdam`, defined in `api/hourly_prices/model.py`), never in the timezone of the host: Vercel runs in UTC, so `datetime.now().astimezone()` used to shift the labels *and* the grey/green split by the DST offset. `APIResponse.get_today_prices()` filters on the same zone.
- **Charts** — `/chart` renders *today's* hours only (00:00–23:59) as a JPEG drawn with Pillow, delivered with `sendPhoto` (`send_telegram_photo`) so it renders inline; bar top corners are rounded. The cheapest and the most expensive bar print their value above the bar (`_draw_extreme_labels`), and `_axis_max` adds `Y_HEADROOM_RATIO` headroom so that label stays inside the plot. A bar is `#d0d0d0` only once its whole hour has elapsed, otherwise `#4caf50`. Text uses Pillow's bundled default font (`ImageFont.load_default(size=...)`), so no system font is required.
- **Storage** — an existing day file is only rewritten when the new data has *more* entries, so recorded hours are never overwritten. `data/` resolves relative to the working directory, so run the CLI from the repo root.
- **Allowlist** — an empty allowlist denies everyone; `TELEGRAM_CHAT_ID` or `TELEGRAM_ALLOWED_CHAT_IDS` must be set for commands to work.
- **Daily digest** — `/api/digest` is triggered by an *external* scheduler (hourly), not by Vercel cron, and only sends when the `MARKET_TIMEZONE` hour equals `DIGEST_HOUR` (default 6), so DST is handled in code rather than by the caller. It refuses to run (`503`) when `DIGEST_SECRET` is unset and requires `X-Digest-Secret`; subscribers live in Upstash Redis (Vercel is read-only) and are intersected with the allowlist before sending. `/digest` previews the message without touching the store.
- **Dependencies** — Vercel and CI build with uv; run `uv sync` after editing deps so `uv.lock` stays in sync.

## Configuration

Read from the environment at runtime (local `.env` is loaded when `python-dotenv` is installed):

| Variable | Required | Description |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | yes | Bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | yes | Fallback chat id for outgoing messages; also the default allowlist |
| `TELEGRAM_ALLOWED_CHAT_IDS` | no | Comma-separated chat ids the webhook may answer |
| `TELEGRAM_WEBHOOK_SECRET` | recommended | Echoed by Telegram in `X-Telegram-Bot-Api-Secret-Token` |
| `UPSTASH_REDIS_REST_URL` | for the digest | Upstash Redis REST endpoint storing the digest subscribers |
| `UPSTASH_REDIS_REST_TOKEN` | for the digest | Upstash Redis REST token paired with the URL |
| `DIGEST_SECRET` | for the digest | Shared secret the scheduler sends in `X-Digest-Secret`; `/api/digest` answers `503` while unset |
| `DIGEST_HOUR` | no | Local hour (`Europe/Amsterdam`) the digest is delivered at (default `6`) |

## Reference

See `README.md` for the full command table, deployment steps, data-storage format and CI details.
