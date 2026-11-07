"""
Address check: does the address exist, and is it actually for sale?

1. Geocoding (U.S. Census Bureau, free): if the street address can't be
   matched, it may be made up. This is a WEAK signal on its own, because
   the Census database misses some new buildings and unusual addresses.
   A ZIP code that doesn't match the street is also noted.

2. For-sale lookup (optional, RentCast): a common scam copies photos and
   details from a home that is listed FOR SALE and advertises it for rent,
   since the real owner isn't living there to notice. Two of the four
   October 2026 news cases used this trick.
"""

from datetime import datetime, timedelta, timezone

from app.checks.base import CheckOutcome, DetectedSignal
from app.schemas.listing import ListingSubmission
from app.services.externalLookups import Geocoder, SaleListingLookup

recentSaleWindowDays = 180


def runAddressCheck(
    submission: ListingSubmission,
    geocoder: Geocoder | None,
    saleListingLookup: SaleListingLookup | None,
) -> CheckOutcome:
    address = submission.address
    if not address.street:
        return CheckOutcome(checkName="address", ran=False, skipReason="No street address was entered.")
    if not (address.zipCode or (address.city and address.stateCode)):
        return CheckOutcome(checkName="address", ran=False,
                            skipReason="A ZIP code, or a city and state, is needed with the street address.")
    if geocoder is None:
        return CheckOutcome(checkName="address", ran=False, skipReason="Address lookup is turned off on the server.")

    # Errors from the lookups propagate; the router turns them into a
    # "temporarily unavailable" skip instead of a misleading result.
    geocodeResult = geocoder.geocode(address.street, address.city, address.stateCode, address.zipCode)
    detectedSignals: list[DetectedSignal] = []

    if not geocodeResult.found:
        detectedSignals.append(DetectedSignal(
            checkName="address",
            signalCode="ADDRESS_NOT_FOUND",
            severity="low",
            explanation=(
                "This street address could not be matched in the U.S. Census address database. "
                "Some new buildings and unusual addresses are missing from it, so confirm the address "
                "exists on a map before going further."
            ),
            evidence={"geocoder": "us_census"},
        ))
    elif address.zipCode and geocodeResult.zipCode and geocodeResult.zipCode != address.zipCode:
        detectedSignals.append(DetectedSignal(
            checkName="address",
            signalCode="ADDRESS_ZIP_MISMATCH",
            severity="low",
            explanation=(
                f"The street address is in ZIP code {geocodeResult.zipCode}, not {address.zipCode} as listed. "
                f"A mismatch can be a simple typo, but check which location you are actually being offered."
            ),
            evidence={"enteredZip": address.zipCode, "geocodedZip": geocodeResult.zipCode},
        ))

    if saleListingLookup is not None:
        fullAddress = ", ".join(part for part in (address.street, address.city, address.stateCode, address.zipCode) if part)
        saleStatus = saleListingLookup.lookup(fullAddress)
        recentCutoff = datetime.now(timezone.utc) - timedelta(days=recentSaleWindowDays)

        if saleStatus.found and saleStatus.isActive:
            detectedSignals.append(DetectedSignal(
                checkName="address",
                signalCode="ADDRESS_LISTED_FOR_SALE",
                severity="high",
                explanation=(
                    "This address is currently listed for sale. Scammers often copy for-sale homes and advertise "
                    "them as rentals because the owner isn't living there to notice. Contact the listing agent "
                    "on the for-sale listing to confirm whether it is really for rent."
                ),
                evidence={"saleListingActive": True},
            ))
        elif saleStatus.found and saleStatus.lastSeenDate and saleStatus.lastSeenDate >= recentCutoff:
            detectedSignals.append(DetectedSignal(
                checkName="address",
                signalCode="ADDRESS_RECENTLY_FOR_SALE",
                severity="medium",
                explanation=(
                    f"This address was listed for sale within the last {recentSaleWindowDays} days. A recently sold "
                    f"home can legitimately become a rental, but scammers also reuse these listings. Confirm "
                    f"ownership through county property records."
                ),
                evidence={"lastSeenForSale": saleStatus.lastSeenDate.date().isoformat()},
            ))

    return CheckOutcome(checkName="address", ran=True, signals=detectedSignals)
