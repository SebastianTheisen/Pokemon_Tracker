"""Tests der Konfiguration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize("secret", ["change-me-in-production", "bitte-aendern", "zu-kurz"])
def test_production_rejects_weak_jwt_secret(secret: str) -> None:
    with pytest.raises(ValidationError, match="PT_JWT_SECRET"):
        Settings(environment="production", jwt_secret=secret)


def test_production_accepts_strong_secret_and_development_allows_default() -> None:
    Settings(environment="production", jwt_secret="a" * 64)
    Settings(environment="development")


def test_catalog_languages_default_to_all_six() -> None:
    assert Settings().catalog_languages == ["de", "en", "ja", "ko", "zh-tw", "zh-cn"]
