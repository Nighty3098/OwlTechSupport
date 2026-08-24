# OwlTechSupport

Telegram-бот техподдержки проекта [owl](https://owl-tech.vercel.app/): приём баг репортов и предложений фич, выдача тикетов команде разработчиков в чат/топик.

## Стек

- Python 3.14+, [aiogram 3](https://docs.aiogram.dev/)
- SQLAlchemy 2 (asyncio) + PostgreSQL (asyncpg)
- Docker + docker compose
- pytest

## Возможности

- `/start` — выбор языка (🇷🇺 🇬🇧 🇯🇵 🇨🇳 🇪🇸 🇩🇪), все тексты — в `app/locales/locale_*.json`.
- **Юзер:** баг репорт / предложение фичи — можно отправлять несколько сообщений с текстом, фото и файлами; заявка сохраняется в БД и уходит в чат поддержки.
- **Разработчики/админы:** список тикетов со сменой статуса (`Not started → In Dev → Completed`), управление командой (список / добавить / удалить участника по @username, user_id или пересланному сообщению).
- Поддержка обычного чата **и топика** (форума).
- Опциональный прокси `socks5://` / `http(s)://` для контейнера.

## Быстрый старт

```bash
cp .env.example .env   # заполните BOT_TOKEN, SUPERADMIN_IDS, SUPPORT_CHAT_ID, пароль БД
docker compose up -d --build
```

Локально без Docker:

```bash
python3.14 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export POSTGRES_HOST=localhost
python -m app
```

## Переменные окружения (.env)

| Переменная | Описание |
| --- | --- |
| `BOT_TOKEN` | токен из @BotFather |
| `SUPERADMIN_IDS` | id админов через запятую (управляют командой) |
| `SUPPORT_CHAT_ID` | чат тикетов: `3800802201`, `-100...`, `@group` или ссылка `https://t.me/c/<id>/<topic>` |
| `SUPPORT_TOPIC_ID` | явный topic id (перекрывает topic из ссылки) |
| `PROXY_URL` | опционально: `socks5://user:pass@host:1080`, `http://...`, `https://...` |
| `POSTGRES_HOST/PORT/USER/PASSWORD/DB` | параметры БД |
| `SUPPORT_CONTACT_URL` | контакт в меню «связаться с разработчиком» |

Docker Compose берёт переменные только из `.env`.

## Структура проекта

```
app/
├── config.py          # env-конфиг, валидация proxy и chat/topic
├── main.py            # сборка диспетчера (middlewares + routers)
├── __main__.py        # запуск polling
├── db/                # engine, models (users, developers, bugs, features)
├── filters/           # IsDeveloper
├── handlers/
│   ├── start.py       # /start, выбор языка, главные меню
│   ├── user.py        # баг репорт / фича / контакт
│   └── admin/         # команда и тикеты
├── keyboards/         # inline-клавиатуры и CallbackData
├── middlewares/       # DbSession, UserContext (+i18n)
├── services/          # repo, i18n, tickets, members
└── locales/           # locale_ru.json ... locale_de.json
tests/                 # pytest (unit + e2e через мок Telegram session)
```

## Разработка

```bash
pip install -r requirements-dev.txt
ruff check app tests   # линт
pytest                 # тесты
```

CI: GitHub Actions прогоняет ruff + pytest на push/PR и автоматически перегенерирует `THIRD_PARTY_NOTICES.md` (pip-licenses).

## Коммиты

Conventional Commits: `feat(scope): ...`, `fix: ...`, `chore: ...`. Шаблон PR — `.github/pull_request_template.md`.
