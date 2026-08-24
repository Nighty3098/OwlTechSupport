"""Tests for the JSON i18n helper."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.config import ConfigError
from app.services.i18n import Translator

EXPECTED_LANGUAGES = {"ru", "en", "ja", "zh", "es", "de"}


@pytest.fixture()
def translator() -> Translator:
    return Translator()


def test_all_six_languages_loaded(translator: Translator):
    assert EXPECTED_LANGUAGES.issubset(set(translator.languages))


def test_locales_have_identical_keysets(translator: Translator):
    keysets = {lang: set(data) for lang, data in translator.translations.items()}
    reference = keysets["en"]
    for lang, keys in keysets.items():
        assert keys == reference, f"locale_{lang} differs from en"


def test_get_returns_translation(translator: Translator):
    text = translator.get("ru", "ticket_sent")
    assert "✅" in text
    assert "{" not in text


def test_formatting_kwargs(translator: Translator):
    for lang in EXPECTED_LANGUAGES:
        rendered = translator.get(lang, "admin_welcome", count=7)
        assert "{count}" not in rendered
        assert "7" in rendered


def test_fallback_to_english(translator: Translator):
    assert translator.get("xx", "cancelled") == translator.get("en", "cancelled")


def test_unknown_key_returns_key_itself(translator: Translator):
    assert translator.get("ru", "no_such_key") == "no_such_key"


def test_bound_translator(translator: Translator):
    t = translator.bound("de")
    assert t("btn_tickets") == translator.get("de", "btn_tickets")


def test_missing_locales_dir_raises():
    empty_translator = Translator(Path("/nonexistent"))
    with pytest.raises(ConfigError, match="No locale"):
        _ = empty_translator.translations


def test_team_entry_template_shape(translator: Translator):
    entry = translator.get(
        "en",
        "team_entry",
        username="dev",
        user_id=123,
        added_by="boss",
        added_at="01.01.2026 10:00 UTC",
    )
    lines = entry.splitlines()
    assert lines[0] == "@dev"
    assert lines[1] == "123"
    assert "Added by @boss" in lines[2]
    assert lines[3] == "Added at: 01.01.2026 10:00 UTC"
