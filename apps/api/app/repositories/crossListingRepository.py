"""
Looks for the same contact details or the same description on earlier
listings at a DIFFERENT address.

Contacts are compared by their keyed hashes (never the raw values).
Descriptions are compared two ways:
  - exact: the SHA-256 fingerprint of the normalized, redacted text
  - near-exact: Postgres trigram similarity (pg_trgm), which scores how
    many 3-letter chunks two texts share. `%` uses the GIN trigram index
    to find candidates quickly, then similarity() keeps only very close ones.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from psycopg_pool import ConnectionPool

nearDuplicateSimilarity = 0.85
lookbackDays = 365


@dataclass(frozen=True)
class EarlierListing:
    zipCode: str | None
    streetAddress: str | None
    createdAt: datetime


@dataclass(frozen=True)
class ContactReuse:
    kind: str                       # "email" or "phone"
    earlierListings: list[EarlierListing]


class CrossListingFinder(Protocol):
    def findContactReuse(self, contactHashes: dict[str, str]) -> list[ContactReuse]:
        """contactHashes maps each hash to its kind ("email" or "phone")."""
        ...

    def findDescriptionReuse(self, fingerprint: str, redactedDescription: str) -> list[EarlierListing]:
        ...


class PostgresCrossListingFinder:
    def __init__(self, connectionPool: ConnectionPool):
        self.connectionPool = connectionPool

    def findContactReuse(self, contactHashes: dict[str, str]) -> list[ContactReuse]:
        if not contactHashes:
            return []
        reuses: list[ContactReuse] = []
        with self.connectionPool.connection() as connection, connection.cursor() as cursor:
            for valueHmac, kind in contactHashes.items():
                cursor.execute(
                    """
                    select distinct on (l.id) l.zip_code, l.street_address, l.created_at
                    from public.listing_contacts c
                    join public.listings l on l.id = c.listing_id
                    where c.kind = %s::public.contact_kind
                      and c.value_hmac = %s
                      and l.created_at > now() - make_interval(days => %s)
                    order by l.id
                    limit 50
                    """,
                    (kind, valueHmac, lookbackDays),
                )
                earlierListings = [EarlierListing(*row) for row in cursor.fetchall()]
                if earlierListings:
                    reuses.append(ContactReuse(kind, earlierListings))
        return reuses

    def findDescriptionReuse(self, fingerprint: str, redactedDescription: str) -> list[EarlierListing]:
        with self.connectionPool.connection() as connection, connection.cursor() as cursor:
            # Very short texts ("2BR for rent") match too easily to mean anything
            if len(redactedDescription) < 80:
                cursor.execute(
                    """
                    select zip_code, street_address, created_at from public.listings
                    where description_fingerprint = %s and created_at > now() - make_interval(days => %s)
                    limit 50
                    """,
                    (fingerprint, lookbackDays),
                )
            else:
                cursor.execute(
                    """
                    select zip_code, street_address, created_at from public.listings
                    where created_at > now() - make_interval(days => %s)
                      and (description_fingerprint = %s
                           or (description_redacted operator(extensions.%%) %s
                               and extensions.similarity(description_redacted, %s) >= %s))
                    limit 50
                    """,
                    (lookbackDays, fingerprint, redactedDescription, redactedDescription, nearDuplicateSimilarity),
                )
            return [EarlierListing(*row) for row in cursor.fetchall()]
