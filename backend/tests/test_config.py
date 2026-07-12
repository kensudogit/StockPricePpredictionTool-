"""Tests for app.config"""

from __future__ import annotations

import unittest

from app.config import Settings, to_async_database_url, to_sync_database_url


class TestDatabaseUrlNormalization(unittest.TestCase):
    def test_postgres_scheme_to_asyncpg(self):
        self.assertEqual(
            to_async_database_url("postgres://u:p@h/db"),
            "postgresql+asyncpg://u:p@h/db",
        )

    def test_postgresql_to_asyncpg(self):
        self.assertEqual(
            to_async_database_url("postgresql://u:p@h/db"),
            "postgresql+asyncpg://u:p@h/db",
        )

    def test_asyncpg_idempotent(self):
        url = "postgresql+asyncpg://u:p@h/db"
        self.assertEqual(to_async_database_url(url), url)

    def test_sync_strips_asyncpg(self):
        self.assertEqual(
            to_sync_database_url("postgresql+asyncpg://u:p@h/db"),
            "postgresql://u:p@h/db",
        )


class TestSettings(unittest.TestCase):
    def test_default_trading_mode_paper(self):
        s = Settings(
            _env_file=None,
            database_url="postgresql://u:p@localhost/db",
        )
        self.assertEqual(s.trading_mode, "paper")
        self.assertTrue(s.database_url.startswith("postgresql+asyncpg://"))

    def test_cors_origins_split(self):
        s = Settings(
            _env_file=None,
            api_cors_origins="http://a.com, http://b.com",
        )
        self.assertEqual(s.cors_origins, ["http://a.com", "http://b.com"])
