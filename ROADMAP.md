# Project Roadmap: Zonneplan Telegram Bot

This roadmap outlines the planned architectural improvements, feature expansions, and DevOps enhancements for the Zonneplan Telegram bot.

---

## Phase 1: Code Quality & Architecture Hardening
*Target duration: 2 Weeks*

- [ ] **Type Safety:** Add comprehensive type annotations across all modules and integrate `mypy` in strict mode.
- [ ] **Linting & Formatting:** Standardize code formatting and linting rules using `ruff`.
- [ ] **Robust Error Recovery:** Implement exponential backoff retry decorators (`tenacity`) for Zonneplan API and Telegram webhook/polling requests.
- [ ] **Configuration Validation:** Migrate environment variable handling to `pydantic-settings` with strict startup validation.
- [ ] **Structured Logging:** Adopt structured JSON logging for easier debugging and log aggregation.

---

## Phase 2: Feature Development & Telemetry
*Target duration: 3 Weeks*

- [ ] **Dynamic Pricing Alerts:** Add automated push notifications for negative or high energy tariff spikes.
- [ ] **Performance Digests:** Implement daily and weekly automated summaries covering solar yield, grid exchange, and battery state-of-charge metrics.
- [ ] **Interactive Inline Keyboards:** Redesign command responses using Telegram inline keyboards for smoother navigation and quick actions.
- [ ] **Caching Layer:** Introduce lightweight TTL caching for frequent API queries to prevent rate-limiting.

---

## Phase 3: DevOps, Containerization & CI/CD
*Target duration: 2 Weeks*

- [ ] **Multi-Stage Dockerfile:** Build a secure, lightweight, non-root Python container image.
- [ ] **Docker Compose Setup:** Provide local deployment orchestration with persistent volume mounts for logs and state.
- [ ] **GitHub Actions CI Pipeline:** Automate code linting, type-checking, and test execution on every pull request.
- [ ] **Automated Container Publishing:** Configure CD workflows to build and push container images to a private/public registry on tagged releases.
