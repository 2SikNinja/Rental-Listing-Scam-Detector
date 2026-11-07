"""
Finds earlier listings whose photos look like the ones just uploaded.

Matching runs in Postgres: `#` is XOR on bit strings, and bit_count()
counts the 1s, so `bit_count(phash # :new)` is the Hamming distance.

Performance note: this compares against every stored photo (a full
scan). That is fast for thousands of photos. At millions, the usual fix
is to split each hash into bands and index them, or use a BK-tree.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
import uuid

from psycopg_pool import ConnectionPool

from app.services.photoHashing import PhotoHashes

maxPHashDistance = 12
maxDHashDistance = 12
maxMatchesPerPhoto = 20


@dataclass(frozen=True)
class PhotoMatch:
    uploadedPhotoIndex: int
    listingId: uuid.UUID
    zipCode: str | None
    streetAddress: str | None
    contactHashes: frozenset[str]
    firstSeenAt: datetime


class PhotoMatcher(Protocol):
    def findMatches(self, photoHashes: list[PhotoHashes]) -> list[PhotoMatch]:
        ...


class PostgresPhotoMatcher:
    def __init__(self, connectionPool: ConnectionPool):
        self.connectionPool = connectionPool

    def findMatches(self, photoHashes: list[PhotoHashes]) -> list[PhotoMatch]:
        foundMatches: list[PhotoMatch] = []
        with self.connectionPool.connection() as connection, connection.cursor() as cursor:
            for photoIndex, hashes in enumerate(photoHashes):
                cursor.execute(
                    """
                    select l.id, l.zip_code, l.street_address, min(p.created_at),
                           coalesce(array_agg(distinct c.value_hmac) filter (where c.value_hmac is not null), '{}')
                    from public.listing_photos p
                    join public.listings l on l.id = p.listing_id
                    left join public.listing_contacts c on c.listing_id = l.id and c.kind in ('email', 'phone')
                    where p.content_sha256 = %s
                       or (bit_count(p.phash # %s::bit(64)) <= %s and bit_count(p.dhash # %s::bit(64)) <= %s)
                    group by l.id, l.zip_code, l.street_address
                    order by min(p.created_at)
                    limit %s
                    """,
                    (
                        hashes.contentSha256,
                        hashes.pHashBits, maxPHashDistance,
                        hashes.dHashBits, maxDHashDistance,
                        maxMatchesPerPhoto,
                    ),
                )
                for listingId, zipCode, streetAddress, firstSeenAt, contactHashes in cursor.fetchall():
                    foundMatches.append(
                        PhotoMatch(photoIndex, listingId, zipCode, streetAddress, frozenset(contactHashes), firstSeenAt)
                    )
        return foundMatches
