"""
Shared pytest setup.

Sets safe, fake environment values before any app code is imported, so
tests never depend on your real .env file and run the same way locally
and in GitHub Actions. Real environment variables take priority over the
.env file in pydantic-settings, so these always win.
"""

import os

testEnvironment = {
    "APP_ENV": "test",
    "DATABASE_URL": "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
    "SUPABASE_URL": "http://127.0.0.1:54321",
    "CONTACT_HASH_SECRET": "b" * 64,
    "CORS_ALLOWED_ORIGINS": "http://localhost:3000",
    "LLM_ENABLED": "false",
}

for envName, envValue in testEnvironment.items():
    os.environ[envName] = envValue
