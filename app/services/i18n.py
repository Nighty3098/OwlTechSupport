"""Tiny JSON-based i18n helper."""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import cached_property
from pathlib import Path

from ..config import ConfigError

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"
DEFAULT_LANGUAGE = "en"
FALLBACK_LANGUAGE = "en"


class Translator:
    """Loads ``locale_<code>.json`` files and renders strings by key."""

    def __init__(self, locales_dir: Path | None = None) -> None:
        self._dir = locales_dir or LOCALES_DIR
        self._translations: dict[str, dict[str, str]] = {}

    @cached_property
    def translations(self) -> dict[str, dict[str, str]]:
        if not self._translations:
            for path in sorted(self._dir.glob("locale_*.json")):
                lang = path.stem.removeprefix("locale_")
                with path.open(encoding="utf-8") as fp:
                    self._translations[lang] = json.load(fp)
            if not self._translations:
                msg = f"No locale_*.json files found in {self._dir}"
                raise ConfigError(msg)
        return self._translations

    @property
    def languages(self) -> tuple[str, ...]:
        return tuple(self.translations)

    def get(self, lang: str, key: str, **kwargs: object) -> str:
        text = self.translations.get(lang, {}).get(key)
        if text is None:
            text = self.translations.get(FALLBACK_LANGUAGE, {}).get(key, key)
        if kwargs:
            text = text.format(**kwargs)
        return text

    def bound(self, lang: str) -> Callable[..., str]:
        """Return a shortcut ``t(key, **kwargs)`` for a fixed language."""

        def t(key: str, **kwargs: object) -> str:
            return self.get(lang, key, **kwargs)

        t.language = lang  # type: ignore[attr-defined]
        return t


i18n = Translator()
