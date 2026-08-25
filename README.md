# OwlTechSupport

Telegram support bot for the [OWL](https://owl-tech.vercel.app/) project: accepts bug reports and feature requests from users, creates tickets, and forwards them to the developer chat/topic for the team to triage and resolve.

**Repository:** <https://github.com/Nighty3098/OwlTechSupport>

## Stack

- **Python 3.14+** / [aiogram 3](https://docs.aiogram.dev/) (async Telegram framework)
- **SQLAlchemy 2** (async) + **PostgreSQL 17** (asyncpg)
- **Docker** + Docker Compose
- **pytest** for testing

## Features

| Area | Details |
|------|---------|
| **I18n** | 6 languages (RU / EN / JA / ZH / ES / DE) selectable via `/start`. All UI strings live in `app/locales/locale_*.json`. |
| **User flow** | Submit a bug report or feature request: text, photos, videos, documents, and voice messages are accepted. Multiple messages are merged into a single ticket. Albums (media groups) are debounced and merged automatically. |
| **Developer flow** | View the ticket queue with rich previews (author, date, attachments, text snippet). Change status: *Not started → In Dev → Completed*. The developer who picks up a ticket is recorded. |
| **Team management** | List, add, and remove team members by `@username`, numeric `user ID`, or a forwarded message (supports hidden sender names). |
| **Forum support** | Works in plain group chats and in forum topics. |
| **Access control** | Superadmins manage the team. Developers get the admin panel; non-developers in the channel receive a polite denial. |
| **Proxy** | Optional `socks5://` / `http(s)://` proxy via `PROXY_URL` (host-local loopback addresses are rewritten automatically for Docker). |

## Quick start

```bash
git clone https://github.com/Nighty3098/OwlTechSupport.git
cd OwlTechSupport
cp .env.example .env   # fill in BOT_TOKEN, SUPERADMIN_IDS, SUPPORT_CHAT_ID, DB credentials
docker compose up -d --build
```

The bot connects to Telegram via polling and prints a confirmation on startup.

### Without Docker

```bash
python3.14 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export POSTGRES_HOST=localhost
python -m app
```

## Environment variables

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) |
| `SUPERADMIN_IDS` | Comma-separated Telegram user IDs of superadmins (can manage the team) |
| `SUPPORT_CHAT_ID` | Target ticket chat: numeric ID (`3800802201`), `-100…` format, `@group` username, or a `https://t.me/c/<id>/<topic>` link |
| `SUPPORT_TOPIC_ID` | Explicit topic ID (overrides the topic parsed from the link above) |
| `PROXY_URL` | *(optional)* `socks5://user:pass@host:1080`, `http://…`, or `https://…`. For a host-local proxy in Docker: `socks5://host.docker.internal:10808` |
| `POSTGRES_HOST` | PostgreSQL host (default `db` in Docker) |
| `POSTGRES_PORT` | PostgreSQL port (default `5432`) |
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password |
| `POSTGRES_DB` | Database name |
| `SUPPORT_CONTACT_URL` | Link shown in the *Contact developer* menu button |

Docker Compose reads all variables from `.env`.

## Project structure

```
app/
├── config.py            # env config, proxy / chat / topic validation
├── main.py              # dispatcher assembly (middlewares + routers)
├── __main__.py          # entrypoint — seed developers, start polling
├── db/
│   ├── engine.py        # async engine + sessionmaker, DDL init + migrations
│   ├── models.py        # User, Developer, Ticket, Bug, Feature mixins
│   └── enums.py         # UserAction, BugStatus, FeatureStatus, UserRole
├── filters/             # IsDeveloper
├── handlers/
│   ├── start.py         # /start, language selection, main menus
│   ├── user.py          # bug / feature submission (one-shot, album merge)
│   └── admin/
│       ├── access_denied.py  # alert for non-developers on admin buttons
│       ├── team.py      # team list / add / remove
│       └── tickets.py   # ticket list + status transitions
├── keyboards/           # inline keyboards and CallbackData classes
├── locales/             # locale_ru.json … locale_de.json (6 languages)
├── middlewares/
│   ├── user_context.py  # DB session + username sync
│   └── i18n.py          # language-aware translation injection
└── services/
    ├── repo.py          # CRUD, seed_developers, apply_status
    ├── i18n.py           # Translator, StubTranslator
    ├── tickets.py        # format_ticket_summary, build_ticket_text
    └── members.py        # extract_member_ref, resolve_member, add/remove_developer
tests/                    # unit + e2e via FakeSession (no real Telegram)
```

## Development

```bash
pip install -r requirements-dev.txt

ruff check app tests    # lint
pytest -q               # run all tests
```

CI (GitHub Actions) runs `ruff check` + `pytest` on every push and PR, and regenerates `THIRD_PARTY_NOTICES.md` via `pip-licenses`.

## Commit convention

[Conventional Commits](https://www.conventionalcommits.org/): `feat(scope): …`, `fix: …`, `chore: …`. PR template: `.github/pull_request_template.md`.
