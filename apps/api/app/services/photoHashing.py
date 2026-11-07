"""
Perceptual hashing for listing photos.

A normal hash (like SHA-256) changes completely if one pixel changes, so
it only catches byte-for-byte identical files. Scammers usually re-save,
resize, or crop stolen photos, which defeats that.

A perceptual hash summarizes what the image LOOKS like in 64 bits:
  - pHash: shrinks the image, then keeps the broad light/dark structure
    (using a frequency transform, like JPEG compression does)
  - dHash: records whether each pixel is brighter than its neighbor

Two photos are "the same picture" when their hashes differ in only a few
of the 64 bits (the Hamming distance). Requiring BOTH hashes to be close
cuts down on false matches between different but similar-looking rooms.
"""

from dataclasses import dataclass
import hashlib

import imagehash
from PIL import Image, ImageOps

from app.security.uploadValidation import ValidatedPhoto

hashSizeBits = 64


@dataclass(frozen=True)
class PhotoHashes:
    contentSha256: str  # exact-file fingerprint
    pHashBits: str      # 64 characters of "0"/"1", stored as Postgres bit(64)
    dHashBits: str
    widthPx: int
    heightPx: int


def imageHashToBits(imageHash: imagehash.ImageHash) -> str:
    return "".join("1" if bitValue else "0" for bitValue in imageHash.hash.flatten())


def hammingDistance(firstBits: str, secondBits: str) -> int:
    """Number of positions where two equal-length bit strings differ."""
    return sum(firstBit != secondBit for firstBit, secondBit in zip(firstBits, secondBits))


def hashPhoto(validatedPhoto: ValidatedPhoto) -> PhotoHashes:
    # Phones often save photos sideways with a "rotate me" tag (EXIF).
    # Applying it first means a rotated copy hashes the same as the original.
    uprightImage: Image.Image = ImageOps.exif_transpose(validatedPhoto.image)
    rgbImage = uprightImage.convert("RGB")

    return PhotoHashes(
        contentSha256=hashlib.sha256(validatedPhoto.imageBytes).hexdigest(),
        pHashBits=imageHashToBits(imagehash.phash(rgbImage)),
        dHashBits=imageHashToBits(imagehash.dhash(rgbImage)),
        widthPx=rgbImage.width,
        heightPx=rgbImage.height,
    )
