"""
Contact check: is the contact information disposable or reused?

1. Throwaway email domains (a public list of about 10,000 domains, like
   mailinator.com). Real landlords and property managers don't use
   addresses that expire in an hour.
2. VoIP phone numbers (optional, Twilio Lookup). Internet numbers can be
   created anonymously in seconds. Many honest businesses use them too,
   so this counts for little on its own.
3. The same phone number or email on earlier listings at DIFFERENT
   addresses. Property managers legitimately do this, so it is a low
   signal. It mostly adds context to other red flags.

Contacts are compared by keyed hash only. The explanation never reveals
which listings matched or where they were.
"""

from functools import lru_cache
from pathlib import Path

from app.checks.base import CheckOutcome, DetectedSignal
from app.config import apiRootDir
from app.repositories.crossListingRepository import CrossListingFinder, EarlierListing
from app.schemas.listing import ListingSubmission
from app.security.privacy import RedactedListing
from app.services.externalLookups import PhoneLineTypeLookup

disposableDomainsPath = apiRootDir / "data" / "disposableEmailDomains.txt"
maxPhoneLookups = 2  # each Twilio lookup costs money, so only the first numbers are checked


@lru_cache
def loadDisposableDomains(listPath: Path = disposableDomainsPath) -> frozenset[str]:
    with listPath.open(encoding="utf-8") as listFile:
        return frozenset(
            line.strip().lower() for line in listFile if line.strip() and not line.startswith("#")
        )


def isDisposableDomain(emailDomain: str, disposableDomains: frozenset[str]) -> bool:
    """Also catches subdomains, like anything.mailinator.com."""
    domainParts = emailDomain.lower().split(".")
    return any(".".join(domainParts[index:]) in disposableDomains for index in range(len(domainParts) - 1))


def normalizeStreet(streetAddress: str | None) -> str | None:
    if not streetAddress:
        return None
    return " ".join(streetAddress.lower().replace(".", "").replace(",", "").split())


def isDifferentAddress(submission: ListingSubmission, earlierListing: EarlierListing) -> bool:
    currentZip, currentStreet = submission.address.zipCode, normalizeStreet(submission.address.street)
    earlierStreet = normalizeStreet(earlierListing.streetAddress)
    if currentZip and earlierListing.zipCode and currentZip != earlierListing.zipCode:
        return True
    return bool(currentStreet and earlierStreet and currentStreet != earlierStreet)


def runContactCheck(
    submission: ListingSubmission,
    redactedListing: RedactedListing,
    crossListingFinder: CrossListingFinder | None,
    phoneLineTypeLookup: PhoneLineTypeLookup | None,
) -> tuple[CheckOutcome, dict[str, str]]:
    """
    Returns the outcome plus line types found ({contact hash: line type}),
    so they can be saved with the hashed contacts.
    """
    emailContacts = [contact for contact in redactedListing.contacts if contact.kind == "email"]
    phoneContacts = [contact for contact in redactedListing.contacts if contact.kind == "phone"]
    if not emailContacts and not phoneContacts:
        return CheckOutcome(checkName="contact", ran=False,
                            skipReason="No email address or phone number was found in the listing."), {}

    detectedSignals: list[DetectedSignal] = []
    lineTypesByHash: dict[str, str] = {}

    disposableDomains = loadDisposableDomains()
    throwawayDomains = sorted({
        contact.emailDomain for contact in emailContacts
        if contact.emailDomain and isDisposableDomain(contact.emailDomain, disposableDomains)
    })
    if throwawayDomains:
        detectedSignals.append(DetectedSignal(
            checkName="contact",
            signalCode="DISPOSABLE_EMAIL",
            severity="medium",
            explanation=(
                f"The email address uses a throwaway domain ({', '.join(throwawayDomains)}). These inboxes are "
                f"anonymous and often expire within hours, which no real landlord would rely on."
            ),
            evidence={"domains": throwawayDomains},
        ))

    if phoneLineTypeLookup is not None:
        for phoneContact in phoneContacts[:maxPhoneLookups]:
            phoneDigits = redactedListing.phoneDigitsByHash.get(phoneContact.valueHmac)
            if phoneDigits:
                lineTypesByHash[phoneContact.valueHmac] = phoneLineTypeLookup.lookupLineType(phoneDigits)
        if "voip" in lineTypesByHash.values():
            detectedSignals.append(DetectedSignal(
                checkName="contact",
                signalCode="VOIP_PHONE_NUMBER",
                severity="medium",
                explanation=(
                    "The phone number is an internet (VoIP) number. These can be created anonymously in seconds, "
                    "which scammers rely on, though many legitimate businesses use them too."
                ),
                evidence={"lineType": "voip"},
            ))

    if crossListingFinder is not None:
        hashesToKinds = {contact.valueHmac: contact.kind for contact in emailContacts + phoneContacts}
        reusedKinds: set[str] = set()
        otherAddressCount = 0
        for contactReuse in crossListingFinder.findContactReuse(hashesToKinds):
            differentAddressListings = [
                earlier for earlier in contactReuse.earlierListings if isDifferentAddress(submission, earlier)
            ]
            if differentAddressListings:
                reusedKinds.add(contactReuse.kind)
                otherAddressCount = max(otherAddressCount, len(differentAddressListings))
        if reusedKinds:
            kindText = " and ".join("phone number" if kind == "phone" else "email" for kind in sorted(reusedKinds, reverse=True))
            listingWord = "listing" if otherAddressCount == 1 else "listings"
            detectedSignals.append(DetectedSignal(
                checkName="contact",
                signalCode="CONTACT_REUSED_ELSEWHERE",
                severity="low",
                explanation=(
                    f"The same {kindText} appeared on {otherAddressCount} earlier {listingWord} at a different "
                    f"address. Property managers do this legitimately, but scammers also reuse contacts across "
                    f"fake listings, so weigh this with the other findings."
                ),
                evidence={"contactKinds": sorted(reusedKinds), "otherAddressCount": otherAddressCount},
            ))

    return CheckOutcome(checkName="contact", ran=True, signals=detectedSignals), lineTypesByHash


def findDescriptionReuseSignals(
    submission: ListingSubmission,
    redactedListing: RedactedListing,
    crossListingFinder: CrossListingFinder | None,
) -> list[DetectedSignal]:
    """
    Copied listing text at a different address. Reported under the text
    check, since it is about the description.
    """
    if crossListingFinder is None:
        return []
    earlierListings = crossListingFinder.findDescriptionReuse(
        redactedListing.descriptionFingerprint, redactedListing.descriptionRedacted
    )
    differentAddressListings = [earlier for earlier in earlierListings if isDifferentAddress(submission, earlier)]
    if not differentAddressListings:
        return []
    # If this same address posted the text FIRST, this is most likely the
    # original listing and the others copied it. The original must not be
    # penalized for having been copied.
    sameAddressListings = [earlier for earlier in earlierListings if not isDifferentAddress(submission, earlier)]
    if sameAddressListings and min(earlier.createdAt for earlier in sameAddressListings) < min(
        earlier.createdAt for earlier in differentAddressListings
    ):
        return []
    firstSeen = min(earlier.createdAt for earlier in differentAddressListings).date().isoformat()
    listingWord = "listing" if len(differentAddressListings) == 1 else "listings"
    return [DetectedSignal(
        checkName="text",
        signalCode="DESCRIPTION_REUSED_ELSEWHERE",
        severity="medium",
        explanation=(
            f"This description is nearly identical to {len(differentAddressListings)} earlier {listingWord} at a "
            f"different address (first seen {firstSeen}). Scammers often copy the text of real listings. "
            f"Property companies sometimes reuse templates, so compare the details carefully."
        ),
        evidence={"otherAddressCount": len(differentAddressListings), "firstSeen": firstSeen},
    )]
