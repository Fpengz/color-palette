from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .color import Color, color_payload


MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 20_000_000


class ImageAnalysisError(ValueError):
    pass


def _kmeans(pixels: np.ndarray, clusters: int, iterations: int = 24) -> tuple[np.ndarray, np.ndarray]:
    """Small deterministic weighted-free k-means tailored for a browser demo."""
    count = len(pixels)
    clusters = min(clusters, count)
    # Deterministic farthest-point seeds avoid losing a smaller but distinct color cluster.
    mean = pixels.mean(axis=0)
    centroids = [pixels[np.argmin(((pixels - mean) ** 2).sum(axis=1))].astype(float)]
    while len(centroids) < clusters:
        distances = ((pixels[:, None, :] - np.stack(centroids)[None, :, :]) ** 2).sum(axis=2)
        centroids.append(pixels[np.argmax(distances.min(axis=1))].astype(float))
    centroids = np.stack(centroids)

    labels = np.zeros(count, dtype=int)
    for _ in range(iterations):
        distances = ((pixels[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        new_labels = distances.argmin(axis=1)
        new_centroids = centroids.copy()
        for index in range(clusters):
            members = pixels[new_labels == index]
            if len(members):
                new_centroids[index] = members.mean(axis=0)
        if np.array_equal(labels, new_labels) or np.max(np.abs(new_centroids - centroids)) < 0.5:
            labels = new_labels
            centroids = new_centroids
            break
        labels, centroids = new_labels, new_centroids
    return centroids, labels


def extract_palette(data: bytes, color_count: int = 5) -> dict:
    if not data:
        raise ImageAnalysisError("The uploaded image is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageAnalysisError("Image is larger than the 12 MB demo limit")

    try:
        image = Image.open(BytesIO(data))
        if image.width * image.height > MAX_PIXELS:
            raise ImageAnalysisError("Image dimensions are too large")
        image = ImageOps.exif_transpose(image).convert("RGBA")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageAnalysisError("Upload a valid PNG, JPG, or WebP image") from exc

    image.thumbnail((360, 360), Image.Resampling.LANCZOS)
    rgba = np.asarray(image).reshape(-1, 4)
    opaque = rgba[rgba[:, 3] >= 32, :3]
    if len(opaque) == 0:
        raise ImageAnalysisError("The image contains no visible pixels")

    # Bound CPU/memory while preserving a deterministic sample.
    if len(opaque) > 45_000:
        sample_indices = np.linspace(0, len(opaque) - 1, 45_000, dtype=int)
        opaque = opaque[sample_indices]

    centroids, labels = _kmeans(opaque.astype(float), max(1, min(color_count, 8)))
    counts = np.bincount(labels, minlength=len(centroids))
    order = np.argsort(counts)[::-1]
    total = counts.sum()
    colors = []
    for index in order:
        rgb = np.clip(np.rint(centroids[index]), 0, 255).astype(int)
        payload = color_payload(Color(*rgb.tolist()))
        payload["share"] = round(float(counts[index] / total * 100), 1)
        colors.append(payload)

    return {
        "width": image.width,
        "height": image.height,
        "analyzed_pixels": int(len(opaque)),
        "dominant": colors[0],
        "palette": colors,
    }
