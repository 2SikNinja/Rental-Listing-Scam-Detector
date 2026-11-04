"""
Application settings.

Loads values from apps/api/.env (or real environment variables in
production) and validates them once at startup. If a required secret is
missing or malformed, the app fails immediately with a clear error
instead of failing later in the middle of a request.
"""

from functools import lru_cache
from pathlib import Path
import re
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

apiRootDir = Path(__file__).resolve().parent.parent
envFilePath = apiRootDir / ".env"

hexSecretPattern = re.compile(r"^[0-9a-fA-F]{64,}$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=envFilePath,
        env_file_encoding="utf-8",
        env_ignore_empty=True,   # "KEY=" in .env is treated as not set
        extra="ignore",          # ignore NEXT_PUBLIC_ vars meant for the web app
        populate_by_name=True,   # lets tests build Settings(appEnv="test", ...)
    )

    # General
    appEnv: Literal["development", "test", "production"] = Field(
        default="development", validation_alias="APP_ENV"
    )

    # Database and auth
    databaseUrl: SecretStr = Field(validation_alias="DATABASE_URL")
    supabaseUrl: str = Field(validation_alias="SUPABASE_URL")

    # Privacy: key for HMAC hashing of emails and phone numbers
    contactHashSecret: SecretStr = Field(validation_alias="CONTACT_HASH_SECRET")

    # External services
    geocodingProvider: Literal["census", "google", "mapbox"] = Field(
        default="census", validation_alias="GEOCODING_PROVIDER"
    )
    geocodingApiKey: SecretStr | None = Field(default=None, validation_alias="GEOCODING_API_KEY")
    twilioAccountSid: str | None = Field(default=None, validation_alias="TWILIO_ACCOUNT_SID")
    twilioAuthToken: SecretStr | None = Field(default=None, validation_alias="TWILIO_AUTH_TOKEN")
    llmEnabled: bool = Field(default=False, validation_alias="LLM_ENABLED")
    llmApiKey: SecretStr | None = Field(default=None, validation_alias="LLM_API_KEY")

    # Security limits
    corsAllowedOriginsRaw: str = Field(
        default="http://localhost:3000", validation_alias="CORS_ALLOWED_ORIGINS"
    )
    rateLimitPerMinute: int = Field(default=10, ge=1, le=1000, validation_alias="RATE_LIMIT_PER_MINUTE")
    # True only when running behind a trusted proxy (Cloud Run), so the
    # client IP is read from X-Forwarded-For. Keep false locally.
    trustProxyHeaders: bool = Field(default=False, validation_alias="TRUST_PROXY_HEADERS")

    # Save listings and results to Postgres. Off by default so local
    # development and unit tests need no database.
    persistenceEnabled: bool = Field(default=False, validation_alias="PERSISTENCE_ENABLED")
    maxPhotosPerListing: int = Field(default=10, ge=1, le=20, validation_alias="MAX_PHOTOS_PER_LISTING")
    maxPhotoBytes: int = Field(
        default=5 * 1024 * 1024, ge=1, le=20 * 1024 * 1024, validation_alias="MAX_PHOTO_BYTES"
    )

    # Scoring
    scoringConfigPath: str = Field(
        default="app/scoring/weights.yaml", validation_alias="SCORING_CONFIG_PATH"
    )

    # Market rent data for the price check (built by scripts/loadMarketRents.py).
    # Relative paths are resolved from apps/api/.
    marketRentsPath: str = Field(default="data/marketRents.csv", validation_alias="MARKET_RENTS_PATH")

    # -----------------------------------------------------------------
    # Field-level validation
    # -----------------------------------------------------------------
    @field_validator("contactHashSecret")
    @classmethod
    def validateContactHashSecret(cls, secretValue: SecretStr) -> SecretStr:
        rawSecret = secretValue.get_secret_value()
        if not hexSecretPattern.match(rawSecret):
            raise ValueError(
                "CONTACT_HASH_SECRET must be at least 64 hex characters. Generate one with: "
                'uv run python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return secretValue

    @field_validator("supabaseUrl")
    @classmethod
    def validateSupabaseUrl(cls, urlValue: str) -> str:
        if not urlValue.startswith(("http://", "https://")):
            raise ValueError("SUPABASE_URL must start with http:// or https://")
        return urlValue.rstrip("/")

    # -----------------------------------------------------------------
    # Cross-field validation: optional features must be fully configured
    # if they are turned on.
    # -----------------------------------------------------------------
    @model_validator(mode="after")
    def validateFeatureConfig(self) -> "Settings":
        if self.llmEnabled and self.llmApiKey is None:
            raise ValueError("LLM_ENABLED is true but LLM_API_KEY is empty")

        hasTwilioSid = self.twilioAccountSid is not None
        hasTwilioToken = self.twilioAuthToken is not None
        if hasTwilioSid != hasTwilioToken:
            raise ValueError("Set both TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN, or neither")

        if self.geocodingProvider != "census" and self.geocodingApiKey is None:
            raise ValueError(f"GEOCODING_PROVIDER={self.geocodingProvider} requires GEOCODING_API_KEY")

        if self.appEnv == "production" and "localhost" in self.corsAllowedOriginsRaw:
            raise ValueError("CORS_ALLOWED_ORIGINS must not include localhost in production")

        return self

    # -----------------------------------------------------------------
    # Convenience properties used by the rest of the app
    # -----------------------------------------------------------------
    @property
    def corsAllowedOrigins(self) -> list[str]:
        return [origin.strip() for origin in self.corsAllowedOriginsRaw.split(",") if origin.strip()]

    @property
    def twilioEnabled(self) -> bool:
        return self.twilioAccountSid is not None and self.twilioAuthToken is not None


@lru_cache
def getSettings() -> Settings:
    """Load settings once and reuse them for the life of the process."""
    return Settings()