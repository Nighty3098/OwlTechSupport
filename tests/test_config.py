"""Tests for environment config parsing and validation."""

from __future__ import annotations

import pytest
from app.config import (
    ConfigError,
    parse_chat_target,
    validate_proxy_url,
)


class TestProxyValidation:
    def test_accepts_socks5(self):
        assert validate_proxy_url("socks5://user:pass@127.0.0.1:1080") == (
            "socks5://user:pass@127.0.0.1:1080"
        )

    def test_accepts_https(self):
        assert validate_proxy_url("https://proxy.example.com:8443") == (
            "https://proxy.example.com:8443"
        )

    def test_accepts_http_and_socks5h(self):
        assert validate_proxy_url("http://10.0.0.1:3128")
        assert validate_proxy_url("socks5h://h:1080")

    def test_empty_returns_none(self):
        assert validate_proxy_url(None) is None
        assert validate_proxy_url("   ") is None

    @pytest.mark.parametrize(
        "raw",
        ["ftp://host:21", "just-a-host:1080", "socks5://", "://nope"],
    )
    def test_rejects_invalid(self, raw):
        with pytest.raises(ConfigError):
            validate_proxy_url(raw)


class TestProxyInContainer:
    def test_loopback_rewritten_inside_container(self):
        from app.config import adapt_proxy_url

        adapted = adapt_proxy_url("socks5://127.0.0.1:10808", in_container=True)
        assert adapted == "socks5://host.docker.internal:10808"

    def test_localhost_with_credentials_rewritten(self):
        from app.config import adapt_proxy_url

        adapted = adapt_proxy_url(
            "http://user:pass@localhost:3128", in_container=True
        )
        assert adapted == "http://user:pass@host.docker.internal:3128"

    def test_external_host_kept_as_is(self):
        from app.config import adapt_proxy_url

        raw = "socks5://proxy.example.com:1080"
        assert adapt_proxy_url(raw, in_container=True) == raw
        assert adapt_proxy_url(raw, in_container=False) == raw

    def test_loopback_kept_outside_container(self):
        from app.config import adapt_proxy_url

        raw = "socks5://127.0.0.1:10808"
        assert adapt_proxy_url(raw, in_container=False) == raw


class TestChatTarget:
    def test_private_supergroup_url_with_topic(self):
        target = parse_chat_target("https://t.me/c/3800802201/37")
        assert target is not None
        assert target.chat_id == -1003800802201
        assert target.topic_id == 37

    def test_public_group_url_with_topic(self):
        target = parse_chat_target("https://t.me/owl_support/12")
        assert target is not None
        assert target.chat_id == "@owl_support"
        assert target.topic_id == 12

    def test_public_username_without_topic(self):
        target = parse_chat_target("@owl")
        assert (target.chat_id, target.topic_id) == ("@owl", None)

    def test_unsigned_supergroup_id_gets_prefix(self):
        target = parse_chat_target("3800802201")
        assert target.chat_id == -1003800802201
        assert target.topic_id is None

    def test_signed_id_kept_as_is(self):
        assert parse_chat_target("-1001234567890").chat_id == -1001234567890
        assert parse_chat_target("-42").chat_id == -42

    def test_empty_returns_none(self):
        assert parse_chat_target(None) is None
        assert parse_chat_target("") is None

    def test_garbage_raises(self):
        with pytest.raises(ConfigError):
            parse_chat_target("not-a-chat")


def test_load_config_reads_env(monkeypatch):
    import app.config as cfg

    monkeypatch.setenv("BOT_TOKEN", "111:abc")
    monkeypatch.setenv("SUPERADMIN_IDS", "1, 2,3")
    monkeypatch.setenv("SUPPORT_CHAT_ID", "https://t.me/c/3800802201/37")
    monkeypatch.setenv("POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    monkeypatch.setenv("PROXY_URL", "socks5://u:p@localhost:1080")

    config = cfg.load_config()
    assert config.superadmin_ids == (1, 2, 3)
    assert config.support_chat.chat_id == -1003800802201
    assert config.support_chat.topic_id == 37
    assert config.proxy_url.startswith("socks5://")
    assert config.db.host == "db.internal"
    assert config.db.port == 6543
    assert config.db.url.startswith("postgresql+asyncpg://owl:")


def test_load_config_requires_token(monkeypatch):
    import app.config as cfg

    monkeypatch.delenv("BOT_TOKEN", raising=False)
    with pytest.raises(ConfigError):
        cfg.load_config()


def test_load_config_invalid_admins(monkeypatch):
    import app.config as cfg

    monkeypatch.setenv("BOT_TOKEN", "111:abc")
    monkeypatch.setenv("SUPPORT_CHAT_ID", "-1001234567890")
    monkeypatch.setenv("SUPERADMIN_IDS", "one,two")
    with pytest.raises(ConfigError):
        cfg.load_config()
