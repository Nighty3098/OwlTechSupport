"""Application configuration loaded from environment variables (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

ALLOWED_PROXY_SCHEMES = ("socks5", "socks5h", "socks4", "http", "https")

DEFAULT_CONTACT_URL = "https://owl-tech.vercel.app/"


class ConfigError(Exception):
    """Raised when the environment configuration is invalid."""


def _get_env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not (value and value.strip()):
        msg = f"Missing required environment variable: {name}"
        raise ConfigError(msg)
    return value or ""


@dataclass(frozen=True, slots=True)
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    name: str

    @property
    def url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


@dataclass(frozen=True, slots=True)
class ChatTarget:
    """Support chat destination: a chat id (or @username) with optional topic."""

    chat_id: int | str
    topic_id: int | None = None


def validate_proxy_url(raw: str | None) -> str | None:
    """Validate proxy url. Supported schemes: socks5(h), socks4, http(s).

    Returns the cleaned url or ``None`` when empty.
    Raises :class:`ConfigError` for malformed values.
    """
    if raw is None or not raw.strip():
        return None
    url = raw.strip()
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_PROXY_SCHEMES:
        allowed = ", ".join(ALLOWED_PROXY_SCHEMES)
        msg = (
            f"Unsupported proxy scheme in PROXY_URL={url!r}. "
            f"Allowed schemes: {allowed} (e.g. socks5://user:pass@host:1080)"
        )
        raise ConfigError(msg)
    if not parsed.netloc:
        msg = f"Invalid proxy url PROXY_URL={url!r}: host is missing"
        raise ConfigError(msg)
    return url


def parse_chat_target(raw: str | None) -> ChatTarget | None:
    """Parse SUPPORT_CHAT_ID into a :class:`ChatTarget`.

    Supported formats::

        3800802201                      -> chat -1003800802201 (supergroup id without sign)
        -1003800802201                  -> chat as-is
        @owl_support                    -> public username
        https://t.me/c/3800802201/37    -> private supergroup + topic 37
        https://t.me/owl_support/37     -> public group/channel + topic 37
    """
    if raw is None or not raw.strip():
        return None
    value = raw.strip()

    if value.startswith("@"):
        return ChatTarget(chat_id=value)

    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        parts = [p for p in parsed.path.split("/") if p]
        topic_id = int(parts[-1]) if len(parts) >= 2 else None
        if parts and parts[0] == "c" and len(parts) >= 2:
            return ChatTarget(chat_id=_normalize_chat_id(parts[1]), topic_id=topic_id)
        if parts:
            return ChatTarget(chat_id=f"@{parts[0]}", topic_id=topic_id)
        msg = f"Invalid SUPPORT_CHAT_URL={value!r}"
        raise ConfigError(msg)

    try:
        return ChatTarget(chat_id=_normalize_chat_id(value))
    except ValueError:
        msg = f"Invalid SUPPORT_CHAT_ID={value!r}"
        raise ConfigError(msg) from None


def _normalize_chat_id(value: str) -> int:
    number = int(value)
    # Unsigned supergroup ids must be prefixed with -100 for the Bot API.
    if number > 0 and len(str(number)) >= 10:
        return -int(f"100{number}")
    return number


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    superadmin_ids: tuple[int, ...]
    support_chat: ChatTarget | None
    db: DbConfig
    proxy_url: str | None = None
    contact_url: str = DEFAULT_CONTACT_URL


def load_config() -> Config:
    token = _get_env("BOT_TOKEN", required=True)

    raw_admins = _get_env("SUPERADMIN_IDS")
    try:
        superadmins = tuple(
            int(part.strip()) for part in raw_admins.split(",") if part.strip()
        )
    except ValueError:
        msg = f"Invalid SUPERADMIN_IDS={raw_admins!r}: expected comma-separated integers"
        raise ConfigError(msg) from None

    proxy_url = validate_proxy_url(_get_env("PROXY_URL"))

    support_raw = _get_env("SUPPORT_CHAT_ID") or None
    support_chat = parse_chat_target(support_raw)
    if support_chat is None:
        msg = "SUPPORT_CHAT_ID is required: set a chat id or t.me link in .env"
        raise ConfigError(msg)

    raw_topic = _get_env("SUPPORT_TOPIC_ID").strip()
    if raw_topic:
        if not raw_topic.lstrip("-").isdigit():
            msg = f"Invalid SUPPORT_TOPIC_ID={raw_topic!r}: expected an integer"
            raise ConfigError(msg)
        support_chat = ChatTarget(
            chat_id=support_chat.chat_id,
            topic_id=int(raw_topic),
        )

    db_port_raw = _get_env("POSTGRES_PORT", "5432")
    if not db_port_raw.isdigit():
        msg = f"Invalid POSTGRES_PORT={db_port_raw!r}"
        raise ConfigError(msg)

    db = DbConfig(
        host=_get_env("POSTGRES_HOST", "postgres"),
        port=int(db_port_raw),
        user=_get_env("POSTGRES_USER", "owl"),
        password=_get_env("POSTGRES_PASSWORD", ""),
        name=_get_env("POSTGRES_DB", "owl_support"),
    )

    contact_url = _get_env("SUPPORT_CONTACT_URL", DEFAULT_CONTACT_URL).strip()
    return Config(
        bot_token=token,
        superadmin_ids=superadmins,
        support_chat=support_chat,
        db=db,
        proxy_url=proxy_url,
        contact_url=contact_url or DEFAULT_CONTACT_URL,
    )
