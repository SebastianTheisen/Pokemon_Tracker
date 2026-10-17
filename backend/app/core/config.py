"""Zentrale Konfiguration, geladen aus Umgebungsvariablen bzw. ``.env``."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Alle Einstellungen der Anwendung.

    Jede Variable kann über eine gleichnamige Umgebungsvariable mit dem Präfix
    ``PT_`` gesetzt werden, z. B. ``PT_DATABASE_URL``.
    """

    model_config = SettingsConfigDict(
        env_prefix="PT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = Field(
        default=False,
        description="Logs als JSON ausgeben (für Produktion), sonst lesbare Konsolenausgabe.",
    )

    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+asyncpg://tracker:tracker@localhost:5432/tracker"),
    )
    jwt_secret: SecretStr = Field(default=SecretStr("change-me-in-production"))

    cors_origins: list[str] = Field(default_factory=list)

    cardmarket_listing_enabled: bool = Field(
        default=False,
        description="Optionalen Cardmarket-Angebots-Provider aktivieren (siehe Plan 5.3).",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Gibt die (gecachte) Konfiguration zurück."""
    return Settings()
