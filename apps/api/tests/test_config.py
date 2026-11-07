"""
Tests for app/config.py.

These build Settings directly with keyword arguments and _env_file=None,
so they never read your real .env file and behave the same on your
machine and in GitHub Actions.
"""

import pytest
from pydantic import ValidationError

from app.config import Settings

validHashSecret = "a" * 64


def buildSettings(**overrides) -> Settings:
    """Create Settings from a known-good baseline plus any overrides."""
    baseValues = {
        "appEnv": "test",
        "databaseUrl": "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
        "supabaseUrl": "http://127.0.0.1:54321",
        "contactHashSecret": validHashSecret,
    }
    baseValues.update(overrides)
    return Settings(_env_file=None, **baseValues)


@pytest.fixture(autouse=True)
def clearRealEnvironment(monkeypatch):
    """Remove any real env vars so they can't leak into a test."""
    envNames = [
        "APP_ENV", "DATABASE_URL", "SUPABASE_URL", "CONTACT_HASH_SECRET",
        "GEOCODING_PROVIDER", "RENTCAST_API_KEY", "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN", "LLM_ENABLED", "LLM_API_KEY", "CORS_ALLOWED_ORIGINS",
    ]
    for envName in envNames:
        monkeypatch.delenv(envName, raising=False)


# ---------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------
def testValidSettingsLoad():
    settings = buildSettings()
    assert settings.appEnv == "test"
    assert settings.twilioEnabled is False
    assert settings.llmEnabled is False


def testSecretsAreHiddenWhenPrinted():
    settings = buildSettings()
    assert validHashSecret not in str(settings)
    assert validHashSecret not in repr(settings.contactHashSecret)


def testCorsOriginsAreSplitAndTrimmed():
    settings = buildSettings(corsAllowedOriginsRaw=" https://a.com , https://b.com ,")
    assert settings.corsAllowedOrigins == ["https://a.com", "https://b.com"]


def testSupabaseUrlTrailingSlashIsRemoved():
    settings = buildSettings(supabaseUrl="https://example.supabase.co/")
    assert settings.supabaseUrl == "https://example.supabase.co"


# ---------------------------------------------------------------------
# Hash secret validation (privacy-critical)
# ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "badSecret",
    [
        "replace-with-64-hex-characters",  # the placeholder from .env.example
        "abc123",                          # too short
        "g" * 64,                          # right length, not hex
    ],
)
def testRejectsWeakOrPlaceholderHashSecret(badSecret):
    with pytest.raises(ValidationError, match="CONTACT_HASH_SECRET"):
        buildSettings(contactHashSecret=badSecret)


def testMissingHashSecretFails():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            databaseUrl="postgresql://x",
            supabaseUrl="http://localhost",
        )


# ---------------------------------------------------------------------
# Feature flags must be fully configured when turned on
# ---------------------------------------------------------------------
def testLlmEnabledWithoutKeyFails():
    with pytest.raises(ValidationError, match="LLM_API_KEY"):
        buildSettings(llmEnabled=True)


def testLlmEnabledWithKeyLoads():
    settings = buildSettings(llmEnabled=True, llmApiKey="test-key")
    assert settings.llmEnabled is True


def testTwilioSidWithoutTokenFails():
    with pytest.raises(ValidationError, match="TWILIO"):
        buildSettings(twilioAccountSid="AC123")


def testTwilioEnabledWhenBothSet():
    settings = buildSettings(twilioAccountSid="AC123", twilioAuthToken="token")
    assert settings.twilioEnabled is True


def testUnsupportedGeocoderIsRejected():
    with pytest.raises(ValidationError):
        buildSettings(geocodingProvider="google")


# ---------------------------------------------------------------------
# Production safety
# ---------------------------------------------------------------------
def testProductionRejectsLocalhostCors():
    with pytest.raises(ValidationError, match="localhost"):
        buildSettings(appEnv="production", corsAllowedOriginsRaw="http://localhost:3000")


def testProductionAcceptsRealOrigin():
    settings = buildSettings(appEnv="production", corsAllowedOriginsRaw="https://myapp.vercel.app")
    assert settings.corsAllowedOrigins == ["https://myapp.vercel.app"]
