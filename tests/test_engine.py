"""Tests for engine / session factory wiring."""

from __future__ import annotations

from app.config import DbConfig
from app.db.engine import create_engine


def test_create_engine_uses_db_config_url(db_config: DbConfig):
    engine = create_engine(db_config)
    assert (
        str(engine.url)
        == db_config.url.replace(f":{db_config.password}@", ":***@")
    )
    assert engine.url.get_driver_name() == "asyncpg"
