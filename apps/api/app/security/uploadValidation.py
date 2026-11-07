"""
Validation for uploaded listing photos.

Uploaded files are untrusted. An attacker could send:
  - a huge file, to exhaust memory or disk
  - a script or executable renamed to "photo.jpg"
  - a "decompression bomb": a tiny file that claims to be, say,
    50,000 x 50,000 pixels and needs gigabytes of memory once decoded
  - a corrupted image designed to crash or exploit the decoder

Defenses, in order:
  1. Count and size limits, enforced while reading, so an oversized file
     is rejected without ever being fully loaded.
  2. File type from the first bytes ("magic numbers"), never from the
     file name or the browser-supplied Content-Type, which are both
     controlled by the client.
  3. A pixel limit checked from the image header BEFORE decoding.
  4. A full decode inside a try block, so a malformed file is rejected
     instead of crashing the request.

Photos are only kept long enough to hash them. They are never saved to
the database or to storage; the web server's temporary upload buffer is
discarded when the request ends.
"""

from dataclasses import dataclass
import io

from PIL import Image, UnidentifiedImageError

# JPEG, PNG, and WebP cover what listing sites use
magicNumbers = {
    "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
}
maxImagePixels = 40_000_000       # about 7,000 x 5,700; real listing photos are far smaller
minImageSide = 32                 # anything smaller can't be meaningfully compared
readChunkBytes = 64 * 1024

# Pillow's own built-in bomb guard, set to the same limit as a second layer
Image.MAX_IMAGE_PIXELS = maxImagePixels


class PhotoRejected(ValueError):
    """Raised with a message that is safe to show the user."""


@dataclass(frozen=True)
class ValidatedPhoto:
    imageFormat: str
    imageBytes: bytes
    image: Image.Image


def detectImageFormat(headerBytes: bytes) -> str | None:
    for imageFormat, prefixes in magicNumbers.items():
        if any(headerBytes.startswith(prefix) for prefix in prefixes):
            return imageFormat
    # WebP: "RIFF" + 4-byte size + "WEBP"
    if headerBytes[:4] == b"RIFF" and headerBytes[8:12] == b"WEBP":
        return "webp"
    return None


def readWithLimit(fileObject, maxBytes: int) -> bytes:
    """Read in chunks and stop as soon as the limit is passed."""
    collectedChunks: list[bytes] = []
    totalBytes = 0
    while True:
        chunk = fileObject.read(readChunkBytes)
        if not chunk:
            break
        totalBytes += len(chunk)
        if totalBytes > maxBytes:
            raise PhotoRejected(f"is larger than the {maxBytes // (1024 * 1024)} MB limit")
        collectedChunks.append(chunk)
    return b"".join(collectedChunks)


def validatePhoto(fileObject, maxBytes: int, pixelLimit: int = maxImagePixels) -> ValidatedPhoto:
    imageBytes = readWithLimit(fileObject, maxBytes)
    if not imageBytes:
        raise PhotoRejected("is empty")

    imageFormat = detectImageFormat(imageBytes[:16])
    if imageFormat is None:
        raise PhotoRejected("is not a JPEG, PNG, or WebP image")

    try:
        # Opening only reads the header, so the size can be checked
        # before any pixels are decoded.
        with Image.open(io.BytesIO(imageBytes)) as headerOnly:
            width, height = headerOnly.size
            if width * height > pixelLimit:
                raise PhotoRejected("has too many pixels to process safely")
            if min(width, height) < minImageSide:
                raise PhotoRejected("is too small to compare")
            if (headerOnly.format or "").lower() != imageFormat:
                raise PhotoRejected("has contents that don't match its image type")

        # Full decode in a fresh object (verify() would make it unusable)
        decodedImage = Image.open(io.BytesIO(imageBytes))
        decodedImage.load()
    except PhotoRejected:
        raise
    except Image.DecompressionBombError as bombError:
        raise PhotoRejected("has too many pixels to process safely") from bombError
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as decodeError:
        raise PhotoRejected("could not be read as an image") from decodeError

    return ValidatedPhoto(imageFormat=imageFormat, imageBytes=imageBytes, image=decodedImage)
