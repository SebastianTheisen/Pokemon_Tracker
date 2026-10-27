"""Zentrale Konfiguration, geladen aus Umgebungsvariablen bzw. ``.env``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
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

    # --- Bildquellen (fehlende Kartenbilder ergänzen) --------------------------
    image_import_interval_days: int = Field(
        default=7, ge=0, description="Bild-Import im Worker alle n Tage; 0 = aus."
    )
    image_import_sources: list[str] = Field(
        default_factory=lambda: ["pokemontcg", "pokemon.com", "jp", "tw"],
        description="pokemontcg (EN-Datensatz), pokemon.com (DE/EN), jp, tw (offizielle DBs).",
    )
    image_import_request_interval_seconds: float = Field(
        default=1.0,
        ge=0,
        le=30,
        description="Kleinster Abstand zweier Anfragen je Server (schnellstes erlaubtes Tempo).",
    )
    image_import_start_intervals: dict[str, float] = Field(
        default_factory=lambda: {"www.pokemon-card.com": 1.0},
        description=(
            "Startabstand je Server; von dort tastet sich der Import nach 100 Erfolgen in "
            "Folge schrittweise bis zum kleinsten Abstand heran (bei Sperre: halbes Tempo)."
        ),
    )
    image_import_host_concurrency: dict[str, int] = Field(
        default_factory=lambda: {"www.pokemon-card.com": 2},
        description="Gleichzeitige Detailseiten je Server (sonst image_import_concurrency).",
    )
    image_import_retry_hours: int = Field(
        default=3, ge=1, description="Abgebrochene Quellen nach so vielen Stunden erneut."
    )
    image_import_concurrency: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Detailseiten gleichzeitig unterwegs (Starts begrenzt der Abstand).",
    )
    image_import_user_agent: str = (
        "Kartenkiste/0.1 (private Sammel-App, 1 Anfrage/s, Bilder werden nicht kopiert)"
    )
    pokemontcg_data_url: str = (
        "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master"
    )
    image_probe_retry_days: int = Field(
        default=30, ge=1, description="Nicht gefundene pokemon.com-Bilder erst danach erneut."
    )
    image_probe_max_per_run: int = Field(default=6000, ge=0)

    # --- One Piece (offizielle Kartenlisten, Phase 8) ----------------------------
    onepiece_sources: dict[str, str] = Field(
        default_factory=lambda: {
            "en": "https://en.onepiece-cardgame.com",
            "ja": "https://www.onepiece-cardgame.com",
        },
        description="Kartenliste je Sprache (Seite /cardlist/, ein Abruf je Set).",
    )
    onepiece_catalog_interval_days: int = Field(
        default=7, ge=0, description="One-Piece-Katalog im Worker alle n Tage; 0 = aus."
    )
    onepiece_request_interval_seconds: float = Field(
        default=1.5, ge=0, le=30, description="Abstand zweier Seitenabrufe (rücksichtsvoll)."
    )

    # --- Cardmarket-Katalog (offizielle Download-Dateien) ----------------------
    cardmarket_catalog_url: str = "https://downloads.s3.cardmarket.com/productCatalog"
    cardmarket_catalog_interval_hours: int = Field(
        default=24, ge=0, description="Katalog + Preisführer im Worker alle n Stunden; 0 = aus."
    )
    # --- Kartendetails aus TCGdex (Seltenheit, Varianten, Illustrator) ---------
    card_details_interval_hours: int = Field(
        default=24, ge=0, description="Fehlende Kartendetails im Worker alle n Stunden; 0 = aus."
    )
    card_details_concurrency: int = Field(default=4, ge=1, le=16)

    cardmarket_set_link_concurrency: int = Field(default=4, ge=1, le=16)
    sealed_images_url: str = "https://tcgcsv.com/tcgplayer"
    sealed_images_interval_days: int = Field(
        default=7, ge=0, description="Bilder für Versiegeltes alle n Tage abgleichen; 0 = aus."
    )
    cardmarket_set_recheck_days: int = Field(
        default=14,
        ge=1,
        description="Sets, für die TCGdex keine Cardmarket-ID kennt, erst danach erneut fragen.",
    )

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
    apify_token: SecretStr | None = Field(
        default=None,
        description="API-Token von Apify (eBay.de-Verkäufe auf Knopfdruck); nur in der .env.",
    )
    psa_token: SecretStr | None = Field(
        default=None,
        description="Token der offiziellen PSA Public API (Zertifikate beim Slab-Scan prüfen).",
    )
    psa_cert_max_age_days: int = Field(
        default=30, ge=1, description="Gemerkte Zertifikate (Population) erst danach erneuern."
    )
    apify_monthly_budget_usd: float = Field(
        default=7.0,
        ge=0,
        description="Kostenbremse: kein neuer Lauf, wenn der Monatsverbrauch das erreichen würde.",
    )
    apify_ebay_actor: str = Field(
        default="epicscrapers/ebay-sold-listings-api",
        description="Dienst aus dem Apify-Store für verkaufte eBay-Artikel (Spike 21.10.2026).",
    )
    apify_ebay_max_items: int = Field(default=20, ge=5, le=60)
    apify_ebay_cache_hours: int = Field(
        default=72, ge=1, description="Gleiche Suche erst danach erneut bezahlen."
    )
    apify_max_charge_usd: float = Field(default=0.15, gt=0, le=2)
    apify_run_timeout_seconds: int = Field(default=120, ge=30, le=600)
    # --- PriceCharting (US-Preise über Apify, nur wo Cardmarket fehlt bzw. für Slabs) ---
    pricecharting_enabled: bool = Field(
        default=True, description="PriceCharting nutzen, wenn ein Apify-Token gesetzt ist."
    )
    pricecharting_actor: str = Field(
        default="gio21/pricecharting-scraper", description="Apify-Dienst für die Suche."
    )
    pricecharting_detail_actor: str = Field(
        default="parsebird/pricecharting-product-scraper",
        description="Apify-Dienst für Produktseiten (Preise je Firma und Note, ~0,003 $).",
    )
    pricecharting_max_items: int = Field(default=3, ge=1, le=10)
    pricecharting_max_charge_usd: float = Field(default=0.03, gt=0, le=1)
    pricecharting_max_age_days: int = Field(
        default=30, ge=1, le=365, description="So lange gilt ein Abruf je Karte."
    )
    pricecharting_reserve_usd: float = Field(
        default=2.0,
        ge=0,
        description="Diesen Teil des Apify-Monatsbudgets nie für PriceCharting nutzen (eBay).",
    )
    pricecharting_catalog_actor: str = Field(
        default="incognito_mode/pricecharting-collection-scraper",
        description="Apify-Dienst für komplette Sets (Kartenliste mit Bildern und Preisen).",
    )
    pricecharting_category_url: str = Field(
        default="https://www.pricecharting.com/category/pokemon-cards",
        description="Übersicht aller Pokémon-Sets bei PriceCharting (Set-Liste).",
    )
    ecb_rates_url: str = Field(
        default="https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
        description="EZB-Referenzkurse (Umrechnung US-Dollar → Euro).",
    )
    extra_price_providers: list[str] = Field(
        default_factory=list,
        description=(
            "Importpfade zusätzlicher Preisquellen (Plug-ins), z. B. "
            "'meine_quelle.provider:MeinProvider' (siehe Plan 5.3)."
        ),
    )

    # --- App (Flutter-Web-Build) --------------------------------------------
    web_dir: Path | None = Field(
        default=None,
        description="Ordner mit dem Flutter-Web-Build; wird unter / ausgeliefert (PWA).",
    )

    # --- Überwachung (Dienst „monitor“, Push über ntfy) --------------------------
    ntfy_url: str = Field(default="https://ntfy.sh", description="ntfy-Server")
    ntfy_topic: SecretStr | None = Field(
        default=None,
        description="Geheimes ntfy-Thema (wie ein Passwort); ohne Thema nur Log-Ausgabe.",
    )
    # --- Web-Push (Preisalarme aufs Handy, PWA) -------------------------------
    push_vapid_private_key: SecretStr | None = Field(
        default=None,
        description="VAPID-Schlüssel (base64url, roh) – erzeugt von deploy/phase7_push.sh.",
    )
    push_subject: str = Field(
        default="mailto:admin@example.com",
        description="Kontakt für die Push-Dienste (https-Adresse der App oder mailto:).",
    )
    monitor_api_url: str = Field(default="http://api:8000/api/v1/health")
    monitor_backup_dir: Path = Field(default=Path("/backups"))
    monitor_interval_minutes: int = Field(default=10, ge=1, le=120)
    monitor_remind_hours: int = Field(
        default=24, ge=1, description="Weiter bestehende Störung so oft erneut melden."
    )
    monitor_backup_max_age_hours: int = Field(default=30, ge=1)
    monitor_heartbeat_max_minutes: int = Field(default=20, ge=5)
    monitor_price_run_max_age_hours: int = Field(default=36, ge=1)
    monitor_cardmarket_max_age_hours: int = Field(default=60, ge=1)
    monitor_min_free_disk_percent: int = Field(default=10, ge=1, le=90)

    # --- Scanner ------------------------------------------------------------
    scanner_data_dir: Path = Field(
        default=Path("data/scanner"),
        description="Volume für Merkmal-Cache und eigene Referenzbilder (keine Fotos).",
    )
    scan_max_upload_mb: int = Field(default=15, ge=1, le=50)
    scan_max_pixels: int = Field(default=40_000_000, ge=1_000_000)
    scan_batch_max: int = Field(default=20, ge=1, le=50)
    scan_rate_limit_per_hour: int = Field(
        default=600, ge=1, description="Bilder pro Nutzer und Stunde (Schutz vor Missbrauch)."
    )
    scan_pending_minutes: int = Field(
        default=30, ge=1, le=240, description="So lange kann ein Scan bestätigt werden."
    )
    scan_log_retention_days: int = Field(default=90, ge=1)
    scanner_concurrency: int = Field(
        default=1, ge=1, le=8, description="Gleichzeitige CPU-Arbeiten (OCR, Bildabgleich)."
    )
    scanner_max_image_candidates: int = Field(default=20, ge=1, le=60)
    scanner_rescue_references: int = Field(
        default=40,
        ge=0,
        le=500,
        description="Ohne lesbaren Text: mit so vielen eigenen Referenzbildern vergleichen.",
    )
    scanner_references_per_card: int = Field(default=5, ge=1, le=20)
    scanner_korean_ocr: bool = Field(
        default=True, description="Koreanisches OCR-Modell bei Bedarf zusätzlich nutzen."
    )
    scanner_image_hosts: list[str] = Field(
        default_factory=lambda: [
            "assets.tcgdex.net",
            "images.pokemontcg.io",
            "images.scrydex.com",
            "assets.pokemon.com",
            "www.pokemon-card.com",
            "asia.pokemon-card.com",
            "storage.googleapis.com",  # Bilder von PriceCharting (Korea, China)
        ],
        description="Nur von diesen Hosts werden Katalogbilder geladen (Schutz vor SSRF).",
    )
    image_proxy_extra_hosts: list[str] = Field(
        default_factory=lambda: [
            "tcgplayer-cdn.tcgplayer.com",
            "product-images.tcgplayer.com",
            "en.onepiece-cardgame.com",  # One-Piece-Kartenbilder (offizielle Kartenliste)
            "www.onepiece-cardgame.com",
        ],
        description="Zusätzlich für die Bildauslieferung erlaubt (Sealed, One Piece).",
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
