# Project Roadmap: Zonneplan Telegram Bot

This roadmap outlines the planned architectural improvements, feature expansions, and DevOps enhancements for the Zonneplan Telegram bot.

> Linting/formatting (`ruff`) and type checking (`ty`) are already enforced through `tox` and the `qualify.yaml` PR workflow, so they are no longer tracked here.

---

## Phase 1: Code Quality & Architecture Hardening

- [ ] **Robust Error Recovery:** Implement exponential backoff retry decorators (`tenacity`) for the Zonneplan API and Telegram API requests. (The bot is webhook-only — there is no polling loop to harden.)
- [ ] **Configuration Validation:** Migrate environment variable handling to `pydantic-settings` with strict startup validation.
- [ ] **Structured Logging:** Adopt structured JSON logging for easier debugging and log aggregation. *(Low priority: Vercel already captures function logs.)*

---

## Phase 2: Feature Development & Telemetry

- [ ] **Dynamic Pricing Alerts:** Add automated push notifications for negative or high energy tariff spikes. Requires a scheduled sender beyond the current hourly archiver, since the webhook cannot self-trigger.
- [ ] **Interactive Inline Keyboards:** Redesign command responses using Telegram inline keyboards for smoother navigation and quick actions.
- [ ] **Caching Layer:** Introduce lightweight TTL caching for frequent API queries to prevent rate-limiting.

---

## Phase 3: Testing & CI/CD

- [ ] **Test Suite:** Add a `pytest` suite and wire test execution into the `qualify.yaml` PR workflow alongside the existing lint/format/type gates.
