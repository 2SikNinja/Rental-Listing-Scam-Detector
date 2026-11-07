"""
Tests for the address check, contact check, and the outside-service
clients they use.

Clients are tested with httpx.MockTransport: requests go to a fake
handler that returns canned responses, so the parsing and error handling
are tested without any network access.
"""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.checks.addressCheck import runAddressCheck
from app.checks.contactCheck import (
    findDescriptionReuseSignals,
    isDisposableDomain,
    loadDisposableDomains,
    runContactCheck,
)
from app.repositories.crossListingRepository import ContactReuse, EarlierListing
from app.schemas.listing import ListingSubmission
from app.security.privacy import prepareListingForStorage
from app.services.externalLookups import (
    CensusGeocoder,
    ExternalLookupError,
    GeocodeResult,
    RentcastSaleListings,
    SaleListingStatus,
    TwilioLineTypeLookup,
    removeUnitDesignator,
)

secretKey = "c" * 64
now = datetime.now(timezone.utc)


def buildSubmission(street="123 Main St", zipCode="91101", **contact):
    return ListingSubmission(
        description="A normal apartment listing with nothing unusual in the wording.",
        address={"street": street, "city": "Pasadena", "stateCode": "CA", "zipCode": zipCode},
        contact=contact,
    )


# ---------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------
class FakeGeocoder:
    def __init__(self, result: GeocodeResult):
        self.result = result
        self.calls = 0

    def geocode(self, street, city, stateCode, zipCode):
        self.calls += 1
        return self.result


class FakeSaleListings:
    def __init__(self, status: SaleListingStatus):
        self.status = status

    def lookup(self, fullAddress):
        return self.status


class FakeLineTypes:
    def __init__(self, lineType: str):
        self.lineType = lineType
        self.lookedUp: list[str] = []

    def lookupLineType(self, phoneDigits):
        self.lookedUp.append(phoneDigits)
        return self.lineType


class FakeCrossListingFinder:
    def __init__(self, contactReuses=(), descriptionMatches=()):
        self.contactReuses = list(contactReuses)
        self.descriptionMatches = list(descriptionMatches)

    def findContactReuse(self, contactHashes):
        return self.contactReuses

    def findDescriptionReuse(self, fingerprint, redactedDescription):
        return self.descriptionMatches


foundInPasadena = GeocodeResult(True, "123 MAIN ST, PASADENA, CA, 91101", "91101", 34.14, -118.14)


def codesOf(outcome):
    return {signal.signalCode for signal in outcome.signals}


# ---------------------------------------------------------------------
# Address check
# ---------------------------------------------------------------------
def testValidAddressHasNoSignals():
    outcome = runAddressCheck(buildSubmission(), FakeGeocoder(foundInPasadena), None)
    assert outcome.ran is True and outcome.signals == []


def testUnknownAddressIsALowSignal():
    outcome = runAddressCheck(buildSubmission(), FakeGeocoder(GeocodeResult(found=False)), None)
    assert codesOf(outcome) == {"ADDRESS_NOT_FOUND"}
    assert outcome.signals[0].severity == "low"


def testZipMismatchIsNoted():
    outcome = runAddressCheck(buildSubmission(zipCode="91106"), FakeGeocoder(foundInPasadena), None)
    assert codesOf(outcome) == {"ADDRESS_ZIP_MISMATCH"}


def testActiveForSaleListingIsHigh():
    outcome = runAddressCheck(buildSubmission(), FakeGeocoder(foundInPasadena),
                              FakeSaleListings(SaleListingStatus(found=True, isActive=True)))
    assert codesOf(outcome) == {"ADDRESS_LISTED_FOR_SALE"}
    assert outcome.signals[0].severity == "high"


def testRecentlyForSaleIsMedium():
    recentStatus = SaleListingStatus(found=True, isActive=False, lastSeenDate=now - timedelta(days=30))
    outcome = runAddressCheck(buildSubmission(), FakeGeocoder(foundInPasadena), FakeSaleListings(recentStatus))
    assert codesOf(outcome) == {"ADDRESS_RECENTLY_FOR_SALE"}


def testOldSaleIsIgnored():
    oldStatus = SaleListingStatus(found=True, isActive=False, lastSeenDate=now - timedelta(days=400))
    outcome = runAddressCheck(buildSubmission(), FakeGeocoder(foundInPasadena), FakeSaleListings(oldStatus))
    assert outcome.signals == []


@pytest.mark.parametrize(
    ("submission", "reasonFragment"),
    [
        (buildSubmission(street=None), "No street address"),
        (ListingSubmission(description="A normal apartment listing description.", address={"street": "1 A St"}),
         "ZIP code, or a city and state"),
    ],
)
def testAddressCheckSkipsWithReason(submission, reasonFragment):
    geocoder = FakeGeocoder(foundInPasadena)
    outcome = runAddressCheck(submission, geocoder, None)
    assert outcome.ran is False and reasonFragment in outcome.skipReason
    assert geocoder.calls == 0  # no outside call when there is nothing to look up


def testUnitNumbersAreRemovedBeforeGeocoding():
    assert removeUnitDesignator("123 Main St Apt 4B") == "123 Main St"
    assert removeUnitDesignator("123 Main St, Unit 12") == "123 Main St"
    assert removeUnitDesignator("123 Main St #7") == "123 Main St"
    assert removeUnitDesignator("123 Main St") == "123 Main St"


# ---------------------------------------------------------------------
# Contact check
# ---------------------------------------------------------------------
def runContact(submission, finder=None, lineTypes=None):
    redacted = prepareListingForStorage(submission, secretKey)
    return runContactCheck(submission, redacted, finder, lineTypes)


def testDisposableEmailIsFlagged():
    outcome, _ = runContact(buildSubmission(email="landlord@mailinator.com"))
    assert codesOf(outcome) == {"DISPOSABLE_EMAIL"}
    assert outcome.signals[0].evidence["domains"] == ["mailinator.com"]


def testDisposableSubdomainIsFlagged():
    assert isDisposableDomain("inbox.mailinator.com", loadDisposableDomains())


@pytest.mark.parametrize("normalDomain", ["gmail.com", "yahoo.com", "outlook.com", "example-properties.com"])
def testCommonEmailDomainsAreNotFlagged(normalDomain):
    assert not isDisposableDomain(normalDomain, loadDisposableDomains())


def testVoipNumberIsFlaggedAndLineTypeReturned():
    lineTypes = FakeLineTypes("voip")
    outcome, lineTypesByHash = runContact(buildSubmission(phone="626-555-0101"), lineTypes=lineTypes)
    assert codesOf(outcome) == {"VOIP_PHONE_NUMBER"}
    assert lineTypes.lookedUp == ["6265550101"]
    assert list(lineTypesByHash.values()) == ["voip"]


def testMobileNumberIsNotFlagged():
    outcome, _ = runContact(buildSubmission(phone="626-555-0101"), lineTypes=FakeLineTypes("mobile"))
    assert outcome.signals == []


def testContactReusedAtDifferentAddressIsLow():
    finder = FakeCrossListingFinder(contactReuses=[
        ContactReuse("phone", [EarlierListing("94063", "9 Oak Ave", now), EarlierListing("91101", "123 Main St", now)])
    ])
    outcome, _ = runContact(buildSubmission(phone="626-555-0101"), finder=finder)
    assert codesOf(outcome) == {"CONTACT_REUSED_ELSEWHERE"}
    assert outcome.signals[0].severity == "low"
    assert outcome.signals[0].evidence["otherAddressCount"] == 1  # the same-address repost doesn't count


def testContactReusedAtSameAddressIsIgnored():
    finder = FakeCrossListingFinder(contactReuses=[ContactReuse("phone", [EarlierListing("91101", "123 main st.", now)])])
    outcome, _ = runContact(buildSubmission(phone="626-555-0101"), finder=finder)
    assert outcome.signals == []


def testContactCheckSkipsWithoutContacts():
    outcome, _ = runContact(buildSubmission())
    assert outcome.ran is False and "No email address or phone number" in outcome.skipReason


def testPhonesInDescriptionAreChecked():
    submission = ListingSubmission(description="Great apartment, text 626-555-0101 to schedule a tour today.")
    lineTypes = FakeLineTypes("voip")
    outcome, _ = runContact(submission, lineTypes=lineTypes)
    assert lineTypes.lookedUp == ["6265550101"]


def testDescriptionReuseAtDifferentAddressIsMedium():
    submission = buildSubmission()
    redacted = prepareListingForStorage(submission, secretKey)
    signals = findDescriptionReuseSignals(
        submission, redacted, FakeCrossListingFinder(descriptionMatches=[EarlierListing("94063", None, now)])
    )
    assert [signal.signalCode for signal in signals] == ["DESCRIPTION_REUSED_ELSEWHERE"]
    assert signals[0].checkName == "text" and signals[0].severity == "medium"


# ---------------------------------------------------------------------
# Outside-service clients (fake HTTP responses)
# ---------------------------------------------------------------------
def clientReturning(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def testCensusGeocoderParsesMatch():
    def handler(request):
        assert request.url.params["benchmark"] == "Public_AR_Current"
        assert "Apt" not in request.url.params["address"]
        return httpx.Response(200, json={"result": {"addressMatches": [{
            "matchedAddress": "123 MAIN ST, PASADENA, CA, 91101",
            "coordinates": {"x": -118.14, "y": 34.14},
            "addressComponents": {"zip": "91101"},
        }]}})

    result = CensusGeocoder(clientReturning(handler)).geocode("123 Main St Apt 4", "Pasadena", "CA", "91101")
    assert result == GeocodeResult(True, "123 MAIN ST, PASADENA, CA, 91101", "91101", 34.14, -118.14)


def testCensusGeocoderNoMatch():
    result = CensusGeocoder(clientReturning(lambda request: httpx.Response(
        200, json={"result": {"addressMatches": []}}))).geocode("1 Nowhere Rd", None, None, "91101")
    assert result.found is False


@pytest.mark.parametrize(
    "badResponse",
    [httpx.Response(503, text="down"), httpx.Response(200, text="<html>not json</html>"), httpx.Response(200, json={})],
)
def testCensusGeocoderErrorsRaiseLookupError(badResponse):
    with pytest.raises(ExternalLookupError):
        CensusGeocoder(clientReturning(lambda request: badResponse)).geocode("1 A St", None, None, "91101")


def testRentcastActiveListing():
    def handler(request):
        assert request.headers["X-Api-Key"] == "test-key"
        return httpx.Response(200, json=[{"status": "Active", "price": 950000, "listedDate": "2026-10-01T00:00:00.000Z"}])

    status = RentcastSaleListings(clientReturning(handler), "test-key").lookup("123 Main St, Pasadena, CA, 91101")
    assert status.found and status.isActive and status.listPrice == 950000


def testRentcastNotFound():
    status = RentcastSaleListings(clientReturning(lambda request: httpx.Response(404)), "k").lookup("x")
    assert status.found is False


def testTwilioMapsVoipTypes():
    def handler(request):
        assert "%2B16265550101" in str(request.url)  # "+" must be encoded
        return httpx.Response(200, json={"line_type_intelligence": {"type": "nonFixedVoip"}})

    assert TwilioLineTypeLookup(clientReturning(handler), "AC1", "token").lookupLineType("6265550101") == "voip"


def testTwilioUnknownTypeIsUnknown():
    lookup = TwilioLineTypeLookup(clientReturning(lambda request: httpx.Response(
        200, json={"line_type_intelligence": {"type": "pager"}})), "AC1", "token")
    assert lookup.lookupLineType("6265550101") == "unknown"


def testOriginalListingIsNotPenalizedForBeingCopied():
    """This address had the text first; a different address copied it later."""
    submission = buildSubmission()
    redacted = prepareListingForStorage(submission, secretKey)
    finder = FakeCrossListingFinder(descriptionMatches=[
        EarlierListing("91101", "123 Main St", now - timedelta(days=10)),   # this address, first
        EarlierListing("94063", "9 Oak Ave", now - timedelta(days=2)),      # copy, later
    ])
    assert findDescriptionReuseSignals(submission, redacted, finder) == []


def testCopyIsStillFlaggedWhenTheOtherAddressWasFirst():
    submission = buildSubmission()
    redacted = prepareListingForStorage(submission, secretKey)
    finder = FakeCrossListingFinder(descriptionMatches=[
        EarlierListing("94063", "9 Oak Ave", now - timedelta(days=10)),     # other address, first
        EarlierListing("91101", "123 Main St", now - timedelta(days=2)),
    ])
    assert len(findDescriptionReuseSignals(submission, redacted, finder)) == 1
