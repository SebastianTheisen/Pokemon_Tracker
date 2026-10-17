"""Zentrale Konfiguration, geladen aus Umgebungsvariablen bzw. ``.env``."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

CatalogLanguage = Literal["de", "en", "ja", "ko", "zh-tw", "zh-cn"]

MIN_JWT_SECRET_LENGTH = 32
_PLACEHOLDER_SECRETS = {"change-me-in-production", "bitte-aendern"}


def _all_catalog_languages() -> list[CatalogLanguage]:
    return ["de", "en", "ja", "ko", "zh-tw", "zh-cn"]


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

    database_url: str = Field(
        default="postgresql+asyncpg://tracker:tracker@localhost:5432/tracker",
        description="SQLAlchemy-URL mit asyncpg-Treiber.",
    )

    # --- Authentifizierung -------------------------------------------------
    jwt_secret: SecretStr = Field(default=SecretStr("change-me-in-production"))
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=120)
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=365)
    invite_ttl_days: int = Field(default=14, ge=1, le=90)
    password_reset_ttl_hours: int = Field(default=24, ge=1, le=168)
    login_rate_limit: int = Field(
        default=5, ge=1, description="Fehlversuche pro E-Mail und IP innerhalb des Zeitfensters."
    )
    login_rate_window_seconds: int = Field(default=300, ge=10)

    cors_origins: list[str] = Field(default_factory=list)

    # --- Katalog -------------------------------------------------------------
    tcgdex_base_url: str = "https://api.tcgdex.net/v2"
    catalog_languages: list[CatalogLanguage] = Field(default_factory=_all_catalog_languages)
    catalog_sync_concurrency: int = Field(default=4, ge=1, le=16)
    http_user_agent: str = "PokemonTracker/0.1 (private Sammel-App)"

    # --- Preise --------------------------------------------------------------
    price_max_age_hours: int = Field(
        default=12, ge=1, le=168, description="Ältere Preise werden beim Ansehen neu geholt."
    )
    price_failure_retry_minutes: int = Field(
        default=60, ge=1, description="Nach einem Fehlschlag frühestens erneut versuchen."
    )
    price_provider_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    price_breaker_threshold: int = Field(
        default=3, ge=1, description="Fehler in Folge, nach denen eine Quelle pausiert."
    )
    price_breaker_pause_minutes: int = Field(default=60, ge=1)
    price_refresh_time: str = Field(
        default="12:30",
        pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
        description=(
            "Tägliche Preisaktualisierung (Ortszeit). TCGdex aktualisiert vormittags (UTC), "
            "deshalb mittags statt nachts."
        ),
    )
    timezone: str = "Europe/Berlin"
    price_tracking_view_days: int = Field(
        default=30, ge=1, description="Angesehene Karten werden so lange täglich mitgeführt."
    )
    price_refresh_concurrency: int = Field(default=4, ge=1, le=16)
    extra_price_providers: list[str] = Field(
        default_factory=list,
        description=(
            "Importpfade zusätzlicher Preisquellen (Plug-ins), z. B. "
            "'meine_quelle.provider:MeinProvider' (siehe Plan 5.3)."
        ),
    )

    @model_validator(mode="after")
    def _require_strong_secret_in_production(self) -> Settings:
        """In Produktion kein Platzhalter- oder zu kurzer JWT-Schlüssel (sonst Tokens fälschbar)."""
        secret = self.jwt_secret.get_secret_value()
        if self.environment == "production" and (
            secret in _PLACEHOLDER_SECRETS or len(secret) < MIN_JWT_SECRET_LENGTH
        ):
            raise ValueError(
                "PT_JWT_SECRET ist in Produktion unsicher: mindestens "
                f"{MIN_JWT_SECRET_LENGTH} Zeichen und kein Platzhalter "
                "(erzeugen z. B. mit `openssl rand -hex 32`)."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Gibt die (gecachte) Konfiguration zurück."""
    return Settings()
