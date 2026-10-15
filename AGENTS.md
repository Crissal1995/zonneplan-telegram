# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project

`zonneplan-telegram` fetches the hourly electricity prices from the Zonneplan consumer API, answers Telegram commands through a webhook, and archives the price history as one JSON file per day.

- **Webhook** — `app.py` → `src/zonneplan_telegram/vercel.py` (FastAPI, `POST /api/webhook`). Answers `/priceNow`, `/priceTomorrow`, `/chart`, `/digest`, `/subscribe`, `/unsubscribe` and `/help` on demand.
- **Analytics** — the webhook folds every answered command into Upstash Redis (`analytics.py`), and `GET /api/analytics` serves the aggregates as JSON to the self-hosted Grafana dashboard in `deploy/grafana/`.
- **Scheduled CLI** — `src/zonneplan_telegram/cli.py` (`update_prices()`). Fetches the prices and archives them to `data/`; run by the `push.yaml` GitHub Action, never by the webhook.
- **Daily digest** — subscribers (`UPSTASH_REDIS_REST_URL`/`_TOKEN`) get a daily message at `DIGEST_HOUR` (06:00 `Europe/Amsterdam`); an external scheduler pings `GET|POST /api/digest` with the `X-Digest-Secret` header.

Python >= 3.12, managed with [uv](https://docs.astral.sh/uv/).

## Commands

```bash
uv sync                     # install / refresh dependencies (uv.lock)
uv run update-prices        # run the scheduled CLI from the repo root
uv run set-webhook <url>    # register the Telegram webhook (… --info, --delete)
uv run pytest               # run the test suite (offline, no credentials needed)
```

Quality gates (also enforced by CI, **run before finishing any change**):

```bash
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest
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
  analytics.py                  # Upstash usage analytics: recording + dashboard summary
  upstash.py                    # Upstash Redis REST client (commands + pipelines)
  chart.py                      # Pillow JPEG bar chart
  storage.py                    # per-day JSON persistence
  api/hourly_prices/            # HTTP calls + pydantic models + Markdown rendering
  telegram/                     # sendMessage / sendPhoto clients, models, set-webhook CLI
data/                           # archived price history, one JSON file per local day
deploy/grafana/                 # self-hosted Grafana (FOSS) for the analytics dashboard
tests/                          # pytest suite (offline: faked Upstash, direct route calls)
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
- **Daily digest** — `/api/digest` is triggered by an *external* scheduler (hourly), not by Vercel cron, and only sends when the `MARKET_TIMEZONE` hour equals `DIGEST_HOUR` (default 6), so DST is handled in code rather than by the caller. It refuses to run (`503`) when `DIGEST_SECRET` is unset and requires `X-Digest-Secret`; subscribers live in Upstash Redis (Vercel is read-only). `/digest` previews the message without touching the store.
- **Dependencies** — Vercel and CI build with uv; run `uv sync` after editing deps so `uv.lock` stays in sync.

## Analytics

- `upstash.py` owns the only Upstash transport: `redis_command()` for one command and `redis_pipeline()` for many in one HTTP round trip (POST to `<url>/pipeline`, replies come back as `{"result"|"error"}` per row). `subscriptions.py` and `analytics.py` both use it — never re-add a private `requests.post` to Upstash.
- `analytics.py:record_command()` folds one event into the aggregates with a single pipeline, and `record_digest()` counts digest deliveries. Both swallow every error: analytics must never break a reply. They are called synchronously from the webhook, so they add one round trip of latency.
- Bucketing uses `MARKET_TIMEZONE` (same trap as the charts): keying on the host clock would shift the daily and hourly aggregates by the DST offset on UTC Vercel.
- Only slash commands are recorded; unknown ones land in the `unknown` bucket (`UNKNOWN_COMMAND` in `commands.py`) and plain text messages are ignored.
- `build_summary()` caches its payload in Redis for 60 s (`…:analytics:summary`) and reads everything in two pipelines, because a dashboard refresh costs ~80 commands against the Upstash quota.
- **Upstash serialises `HGETALL` as a flat array** (`["field", "value", …]`), not as a JSON object — `ZREVRANGE … WITHSCORES` is flat too. `analytics._as_mapping()` accepts both shapes, and the test fake deliberately answers in the flat shape so a dict-only parser cannot come back: it silently yields empty hashes, which reads as "every counter is 0" (the set-backed user counts keep working, since `SCARD` returns an int).
- The endpoint returns arrays for the trend datasets plus an object for `totals`; the Grafana panels therefore set `json_options.root_is_not_array` on the totals queries only.
- Infinity reads the data source base URL from Grafana's **top-level `url` field** — `jsonData.url` is ignored (`LoadSettings`), and a query that stays relative is rejected by the allowed-hosts check (`requested URL not allowed`). A configured base URL makes `allowedHosts` unnecessary, so the provisioning omits it. `deploy/**` is excluded from the Vercel bundle in `vercel.json`.

## Configuration

Read from the environment at runtime (local `.env` is loaded when `python-dotenv` is installed):

| Variable | Required | Description |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | yes | Bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_WEBHOOK_SECRET` | recommended | Echoed by Telegram in `X-Telegram-Bot-Api-Secret-Token` |
| `UPSTASH_REDIS_REST_URL` | for the digest | Upstash Redis REST endpoint storing the digest subscribers |
| `UPSTASH_REDIS_REST_TOKEN` | for the digest | Upstash Redis REST token paired with the URL |
| `DIGEST_SECRET` | for the digest | Shared secret the scheduler sends in `X-Digest-Secret`; `/api/digest` answers `503` while unset |
| `DIGEST_HOUR` | no | Local hour (`Europe/Amsterdam`) the digest is delivered at (default `6`) |
| `ANALYTICS_SECRET` | for the dashboard | Shared secret the Grafana data source sends in `X-Analytics-Secret` (a bearer token is accepted too); `/api/analytics` answers `503` while unset |

## Reference

See `README.md` for the full command table, deployment steps, data-storage format and CI details.
