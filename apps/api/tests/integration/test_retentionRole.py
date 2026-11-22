"""
Integration tests for the retention_job database role.

The daily retention workflow connects as retention_job. These tests
check that the role can run the purge function and is blocked from
everything else. They are skipped unless TEST_RETENTION_DATABASE_URL is
set (CI sets it up with a Postgres container).
"""

import os

import psycopg
import pytest

retentionDatabaseUrl = os.environ.get("TEST_RETENTION_DATABASE_URL")

pytestmark = pytest.mark.skipif(not retentionDatabaseUrl, reason="TEST_RETENTION_DATABASE_URL not set")


def connectAsRetentionJob() -> psycopg.Connection:
    return psycopg.connect(retentionDatabaseUrl, autocommit=True)


def test_retentionRoleCanRunThePurge():
    with connectAsRetentionJob() as connection:
        deletedCount = connection.execute("select public.purge_expired_listings()").fetchone()[0]
    assert isinstance(deletedCount, int)
    assert deletedCount >= 0


@pytest.mark.parametrize("statement", [
    "select count(*) from public.listings",
    "select count(*) from public.listing_contacts",
    "delete from public.listings",
    "update public.listings set purge_after = now()",
    "insert into public.market_rents (zip_code) values ('00000')",
])
def test_retentionRoleCannotTouchTablesDirectly(statement):
    with connectAsRetentionJob() as connection, pytest.raises(psycopg.errors.InsufficientPrivilege):
        connection.execute(statement)
