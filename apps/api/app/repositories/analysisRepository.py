"""
Saves a finished analysis to Postgres.

Everything for one submission (the listing, its hashed contacts, the
analysis, and every signal) is written in ONE transaction. Either all of
it is saved or none of it is, so the database never holds half a result,
like an analysis with missing signals.

All values are passed as query parameters (%s), never pasted into the
SQL string, which prevents SQL injection.
"""

import uuid

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.schemas.listing import ListingSubmission
from app.scoring.engine import ScoreResult
from app.security.privacy import RedactedListing


def saveAnalysis(
    connection: Connection,
    analysisId: uuid.UUID,
    submission: ListingSubmission,
    redactedListing: RedactedListing,
    scoreResult: ScoreResult,
    durationMs: int,
) -> uuid.UUID:
    """Insert everything for one analysis. Returns the new listing ID."""
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            """
            insert into public.listings (
                source, source_domain, title, description_redacted, description_fingerprint,
                monthly_rent_cents, bedrooms, bathrooms,
                street_address, city, state_code, zip_code
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning id
            """,
            (
                submission.source,
                submission.sourceDomain,
                redactedListing.titleRedacted,
                redactedListing.descriptionRedacted,
                redactedListing.descriptionFingerprint,
                submission.monthlyRentCents,
                submission.bedrooms,
                submission.bathrooms,
                submission.address.street,
                submission.address.city,
                submission.address.stateCode,
                submission.address.zipCode,
            ),
        )
        listingId = cursor.fetchone()[0]

        if redactedListing.contacts:
            cursor.executemany(
                """
                insert into public.listing_contacts (listing_id, kind, value_hmac, email_domain)
                values (%s, %s, %s, %s)
                """,
                [
                    (listingId, contact.kind, contact.valueHmac, contact.emailDomain)
                    for contact in redactedListing.contacts
                ],
            )

        cursor.execute(
            """
            insert into public.analyses (
                id, listing_id, status, total_points, risk_level,
                scoring_config_version, duration_ms, completed_at
            )
            values (%s, %s, 'complete', %s, %s, %s, %s, now())
            """,
            (
                analysisId,
                listingId,
                scoreResult.totalPoints,
                scoreResult.riskLevel,
                scoreResult.configVersion,
                durationMs,
            ),
        )

        if scoreResult.scoredSignals:
            cursor.executemany(
                """
                insert into public.signals (analysis_id, check_name, signal_code, severity, points, explanation, evidence)
                values (%s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        analysisId,
                        scored.signal.checkName,
                        scored.signal.signalCode,
                        scored.signal.severity,
                        scored.points,
                        scored.signal.explanation,
                        Jsonb(scored.signal.evidence),
                    )
                    for scored in scoreResult.scoredSignals
                ],
            )

    return listingId
