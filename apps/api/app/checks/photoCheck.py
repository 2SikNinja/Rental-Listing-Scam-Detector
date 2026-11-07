"""
Photo check: flags photos that already appeared on a different listing.

Scammers copy photos from real listings (or old ones) and repost them
with their own address, price, or phone number. If an uploaded photo
matches a photo from an earlier listing that has a DIFFERENT address or
DIFFERENT contact details, that is a strong warning sign.

If the earlier listing had the same address and contacts, it is most
likely the same landlord reposting, so it is noted but not penalized.

Privacy: the explanation never reveals the other listing's address,
contacts, or ID. It only says what differed, so the tool can't be used
to look up other people's submissions.

Limits: it only knows photos that were analyzed by this app, not every
photo on the internet. Heavy crops, mirroring, or overlaid text can also
defeat perceptual hashing.
"""

from app.checks.base import CheckOutcome, DetectedSignal
from app.repositories.photoRepository import PhotoMatch, PhotoMatcher
from app.schemas.listing import ListingSubmission
from app.services.photoHashing import PhotoHashes


def normalizeStreet(streetAddress: str | None) -> str | None:
    if not streetAddress:
        return None
    return " ".join(streetAddress.lower().replace(".", "").replace(",", "").split())


def describeDifferences(match: PhotoMatch, submission: ListingSubmission, contactHashes: frozenset[str]) -> list[str]:
    differences: list[str] = []
    currentZip = submission.address.zipCode
    if currentZip and match.zipCode and currentZip != match.zipCode:
        differences.append("a different ZIP code")
    else:
        currentStreet = normalizeStreet(submission.address.street)
        earlierStreet = normalizeStreet(match.streetAddress)
        if currentStreet and earlierStreet and currentStreet != earlierStreet:
            differences.append("a different street address")
    if contactHashes and match.contactHashes and not (contactHashes & match.contactHashes):
        differences.append("different contact details")
    return differences


def runPhotoCheck(
    submission: ListingSubmission,
    photoHashes: list[PhotoHashes],
    contactHashes: frozenset[str],
    photoMatcher: PhotoMatcher | None,
) -> CheckOutcome:
    if not photoHashes:
        return CheckOutcome(checkName="photo", ran=False, skipReason="No photos were uploaded.")
    if photoMatcher is None:
        return CheckOutcome(checkName="photo", ran=False,
                            skipReason="Photo comparison needs the database, which is not connected.")

    matches = photoMatcher.findMatches(photoHashes)
    if not matches:
        return CheckOutcome(checkName="photo", ran=True)

    suspiciousPhotos: set[int] = set()
    suspiciousListings: set = set()
    differenceReasons: set[str] = set()
    for match in matches:
        differences = describeDifferences(match, submission, contactHashes)
        if differences:
            suspiciousPhotos.add(match.uploadedPhotoIndex)
            suspiciousListings.add(match.listingId)
            differenceReasons.update(differences)

    earliestSeen = min(match.firstSeenAt for match in matches).date().isoformat()
    matchedPhotoCount = len({match.uploadedPhotoIndex for match in matches})

    if suspiciousPhotos:
        photoWord = "photo" if len(suspiciousPhotos) == 1 else "photos"
        listingWord = "listing" if len(suspiciousListings) == 1 else "listings"
        reasonText = " and ".join(sorted(differenceReasons))
        return CheckOutcome(
            checkName="photo",
            ran=True,
            signals=[DetectedSignal(
                checkName="photo",
                signalCode="PHOTO_REUSED_ELSEWHERE",
                severity="high",
                explanation=(
                    f"{len(suspiciousPhotos)} {photoWord} matched {len(suspiciousListings)} earlier {listingWord} "
                    f"with {reasonText}, first seen {earliestSeen}. Scammers often copy photos from real "
                    f"listings and repost them with their own address or contact details."
                ),
                evidence={
                    "matchedPhotoCount": len(suspiciousPhotos),
                    "matchedListingCount": len(suspiciousListings),
                    "differences": sorted(differenceReasons),
                    "firstSeen": earliestSeen,
                },
            )],
        )

    return CheckOutcome(
        checkName="photo",
        ran=True,
        signals=[DetectedSignal(
            checkName="photo",
            signalCode="PHOTO_SEEN_BEFORE_SAME_DETAILS",
            severity="info",
            explanation=(
                f"{matchedPhotoCount} photo(s) were seen before (first {earliestSeen}) on a listing with the same "
                f"address and contact details, which usually means the same landlord reposted it."
            ),
            evidence={"matchedPhotoCount": matchedPhotoCount, "firstSeen": earliestSeen},
        )],
    )
