"""
Tests for upload validation, perceptual hashing, and the photo check.
"""

from datetime import datetime, timezone
import io
import uuid

from PIL import Image
import pytest

from app.checks.photoCheck import runPhotoCheck
from app.repositories.photoRepository import PhotoMatch
from app.schemas.listing import ListingSubmission
from app.security.uploadValidation import PhotoRejected, validatePhoto
from app.services.photoHashing import hammingDistance, hashPhoto
from tests.imageFactory import imageToBytes, makeScene, sceneBytes

fiveMegabytes = 5 * 1024 * 1024


def hashesFromBytes(imageBytes: bytes):
    return hashPhoto(validatePhoto(io.BytesIO(imageBytes), fiveMegabytes))


# ---------------------------------------------------------------------
# Upload validation (untrusted files)
# ---------------------------------------------------------------------
@pytest.mark.parametrize("imageFormat", ["JPEG", "PNG", "WEBP"])
def testAcceptsSupportedFormats(imageFormat):
    validated = validatePhoto(io.BytesIO(sceneBytes(1, imageFormat)), fiveMegabytes)
    assert validated.imageFormat == imageFormat.lower()


def testRejectsNonImageRenamedAsPhoto():
    """File type comes from the bytes, not the name."""
    with pytest.raises(PhotoRejected, match="not a JPEG, PNG, or WebP"):
        validatePhoto(io.BytesIO(b"#!/bin/sh\necho pwned\n" * 10), fiveMegabytes)


def testRejectsOversizedFileWithoutReadingItAll():
    class EndlessFile:
        bytesRead = 0

        def read(self, chunkSize):
            self.bytesRead += chunkSize
            return b"\xff" * chunkSize

    endlessFile = EndlessFile()
    with pytest.raises(PhotoRejected, match="larger than"):
        validatePhoto(endlessFile, 1024 * 1024)
    assert endlessFile.bytesRead <= 1024 * 1024 + 64 * 1024


def testRejectsDecompressionBomb():
    """A small file that claims a huge pixel count is rejected before decoding."""
    bombBytes = imageToBytes(Image.new("1", (12_000, 12_000)), "PNG")  # tiny file, 144M pixels
    assert len(bombBytes) < 1024 * 1024
    with pytest.raises(PhotoRejected, match="too many pixels"):
        validatePhoto(io.BytesIO(bombBytes), fiveMegabytes)


def testRejectsTruncatedImage():
    fullBytes = sceneBytes(1)
    with pytest.raises(PhotoRejected, match="could not be read"):
        validatePhoto(io.BytesIO(fullBytes[: len(fullBytes) // 3]), fiveMegabytes)


def testRejectsTinyImage():
    with pytest.raises(PhotoRejected, match="too small"):
        validatePhoto(io.BytesIO(imageToBytes(Image.new("RGB", (10, 10)), "PNG")), fiveMegabytes)


def testRejectsEmptyFile():
    with pytest.raises(PhotoRejected, match="empty"):
        validatePhoto(io.BytesIO(b""), fiveMegabytes)


# ---------------------------------------------------------------------
# Perceptual hashing
# ---------------------------------------------------------------------
def testHashesAre64Bits():
    hashes = hashesFromBytes(sceneBytes(1))
    assert len(hashes.pHashBits) == 64 and set(hashes.pHashBits) <= {"0", "1"}
    assert len(hashes.dHashBits) == 64
    assert len(hashes.contentSha256) == 64


@pytest.mark.parametrize(
    "editedBytes",
    [
        imageToBytes(makeScene(1), "JPEG", quality=40),            # recompressed
        imageToBytes(makeScene(1).resize((400, 300)), "JPEG"),      # resized
        imageToBytes(makeScene(1), "PNG"),                          # converted
    ],
)
def testEditedCopiesStayClose(editedBytes):
    original = hashesFromBytes(sceneBytes(1, quality=95))
    edited = hashesFromBytes(editedBytes)
    assert hammingDistance(original.pHashBits, edited.pHashBits) <= 4
    assert original.contentSha256 != edited.contentSha256  # an exact-file hash would have missed it


def testDifferentPhotosAreFarApart():
    first, second = hashesFromBytes(sceneBytes(1)), hashesFromBytes(sceneBytes(2))
    assert hammingDistance(first.pHashBits, second.pHashBits) > 16


def testRotationTagIsAppliedBeforeHashing():
    """A phone photo saved sideways with an EXIF rotate tag hashes like the upright original."""
    upright = makeScene(1)
    sideways = upright.rotate(90, expand=True)
    exifData = Image.Exif()
    exifData[0x0112] = 6  # "rotate 90 degrees clockwise to display"
    taggedBytes = imageToBytes(sideways, "JPEG", exif=exifData.tobytes(), quality=95)
    assert hammingDistance(
        hashesFromBytes(imageToBytes(upright, "JPEG", quality=95)).pHashBits,
        hashesFromBytes(taggedBytes).pHashBits,
    ) <= 4


# ---------------------------------------------------------------------
# Photo check logic (with a fake matcher)
# ---------------------------------------------------------------------
class FakePhotoMatcher:
    def __init__(self, matches):
        self.matches = matches

    def findMatches(self, photoHashes):
        return self.matches


def earlierListing(zipCode="91101", street="10 Main St", contactHashes=("abc",)):
    return PhotoMatch(0, uuid.uuid4(), zipCode, street, frozenset(contactHashes),
                      datetime(2026, 10, 1, tzinfo=timezone.utc))


def runCheck(matches, zipCode="91101", street="10 Main St", contactHashes=frozenset({"abc"}), withPhotos=True):
    submission = ListingSubmission(
        description="A normal apartment listing description here.",
        address={"zipCode": zipCode, "street": street},
    )
    photoHashes = [hashesFromBytes(sceneBytes(1))] if withPhotos else []
    return runPhotoCheck(submission, photoHashes, contactHashes, FakePhotoMatcher(matches))


def testDifferentZipIsFlaggedHigh():
    outcome = runCheck([earlierListing(zipCode="94063")])
    assert outcome.signals[0].signalCode == "PHOTO_REUSED_ELSEWHERE"
    assert outcome.signals[0].severity == "high"
    assert "a different ZIP code" in outcome.signals[0].evidence["differences"]


def testDifferentContactsAreFlagged():
    outcome = runCheck([earlierListing(contactHashes=("someoneElse",))])
    assert outcome.signals[0].evidence["differences"] == ["different contact details"]


def testDifferentStreetInSameZipIsFlagged():
    outcome = runCheck([earlierListing(street="99 Oak Ave")])
    assert outcome.signals[0].evidence["differences"] == ["a different street address"]


def testStreetFormattingDifferencesDoNotCount():
    outcome = runCheck([earlierListing(street="10 Main St.")], street="10  main st")
    assert outcome.signals[0].signalCode == "PHOTO_SEEN_BEFORE_SAME_DETAILS"
    assert outcome.signals[0].severity == "info"


def testExplanationNeverRevealsTheOtherListing():
    otherListing = earlierListing(zipCode="94063", street="742 Evergreen Terrace")
    explanation = runCheck([otherListing]).signals[0].explanation
    assert "94063" not in explanation and "Evergreen" not in explanation
    assert str(otherListing.listingId) not in explanation


def testNoMatchesMeansNoSignal():
    outcome = runCheck([])
    assert outcome.ran is True and outcome.signals == []


def testSkippedWithoutPhotos():
    outcome = runCheck([], withPhotos=False)
    assert outcome.ran is False and "No photos" in outcome.skipReason


def testSkippedWithoutDatabase():
    submission = ListingSubmission(description="A normal apartment listing description here.")
    outcome = runPhotoCheck(submission, [hashesFromBytes(sceneBytes(1))], frozenset(), None)
    assert outcome.ran is False and "database" in outcome.skipReason


def testPhotoOwnerIsNotPenalizedWhenOthersCopiedLater():
    original = PhotoMatch(0, uuid.uuid4(), "91101", "10 Main St", frozenset({"abc"}),
                          datetime(2026, 9, 1, tzinfo=timezone.utc))
    laterCopy = PhotoMatch(0, uuid.uuid4(), "94063", "9 Oak Ave", frozenset({"xyz"}),
                           datetime(2026, 10, 15, tzinfo=timezone.utc))
    outcome = runCheck([original, laterCopy])
    assert outcome.signals[0].signalCode == "PHOTO_SEEN_BEFORE_SAME_DETAILS"


def testPhotoCopyIsFlaggedWhenOtherListingWasFirst():
    otherFirst = PhotoMatch(0, uuid.uuid4(), "94063", "9 Oak Ave", frozenset({"xyz"}),
                            datetime(2026, 9, 1, tzinfo=timezone.utc))
    outcome = runCheck([otherFirst])
    assert outcome.signals[0].signalCode == "PHOTO_REUSED_ELSEWHERE"
