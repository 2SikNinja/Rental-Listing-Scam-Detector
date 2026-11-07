"""
Generates realistic-ish test photos in memory, so tests need no image
files in the repo. Each seed draws a different "room" of colored shapes.
"""

import io
import random

from PIL import Image, ImageDraw, ImageFilter


def makeScene(seed: int, size: tuple[int, int] = (800, 600)) -> Image.Image:
    randomGenerator = random.Random(seed)
    sceneImage = Image.new("RGB", size, tuple(randomGenerator.randint(0, 255) for _ in range(3)))
    drawing = ImageDraw.Draw(sceneImage)
    for _ in range(25):
        left, top = randomGenerator.randint(0, size[0]), randomGenerator.randint(0, size[1])
        drawing.rectangle(
            [left, top, left + randomGenerator.randint(40, 300), top + randomGenerator.randint(40, 300)],
            fill=tuple(randomGenerator.randint(0, 255) for _ in range(3)),
        )
    return sceneImage.filter(ImageFilter.GaussianBlur(2))


def imageToBytes(sourceImage: Image.Image, imageFormat: str = "JPEG", **saveOptions) -> bytes:
    outputBuffer = io.BytesIO()
    sourceImage.save(outputBuffer, imageFormat, **saveOptions)
    return outputBuffer.getvalue()


def sceneBytes(seed: int, imageFormat: str = "JPEG", **saveOptions) -> bytes:
    return imageToBytes(makeScene(seed), imageFormat, **saveOptions)
