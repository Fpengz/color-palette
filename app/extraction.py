from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from .color import Color, color_payload
from .errors import CodedError


MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 20_000_000
ROI = tuple[int, int, int, int]
SUPPORTED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
ALPHA_POLICY = "exclude_alpha_below_32; treat_remaining_pixels_as_opaque"
ANIMATION_POLICY = "first_frame_only"
MODEL_VERSION = "rgb-kmeans-prototype-v1"


class ImageAnalysisError(CodedError):
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
        nearest = distances.min(axis=1)
        farthest = int(np.argmax(nearest))
        # An image can hold fewer distinct colors than the requested cluster
        # count; seeding past that point only duplicates existing centroids.
        if nearest[farthest] <= 0:
            break
        centroids.append(pixels[farthest].astype(float))
    centroids = np.stack(centroids)
    clusters = len(centroids)

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


def _analyze_region(image: Image.Image, color_count: int) -> dict:
    analyzed = image.copy()
    analyzed.thumbnail((360, 360), Image.Resampling.LANCZOS)
    rgba = np.asarray(analyzed).reshape(-1, 4)
    opaque = rgba[rgba[:, 3] >= 32, :3]
    if len(opaque) == 0:
        raise ImageAnalysisError("The image contains no visible pixels", code="no_visible_pixels")

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
        # Skip clusters that ended up with no members; they carry a stale seed
        # color and would surface as duplicate 0% swatches.
        if counts[index] == 0:
            continue
        rgb = np.clip(np.rint(centroids[index]), 0, 255).astype(int)
        payload = color_payload(Color(*rgb.tolist()))
        payload["share"] = round(float(counts[index] / total * 100), 1)
        colors.append(payload)

    return {
        "width": analyzed.width,
        "height": analyzed.height,
        "analyzed_pixels": len(opaque),
        "dominant": colors[0],
        "palette": colors,
    }


def _decode_image(data: bytes) -> tuple[Image.Image, dict]:
    try:
        source = Image.open(BytesIO(data))
        image_format = (source.format or "").upper()
        if image_format not in SUPPORTED_FORMATS:
            supported = ", ".join(sorted(SUPPORTED_FORMATS))
            raise ImageAnalysisError(
                f"Decoded image format {image_format or 'unknown'} is not supported; use {supported}",
                code="unsupported_format",
                format=image_format or "unknown",
                supported=sorted(SUPPORTED_FORMATS),
            )

        frame_count = int(getattr(source, "n_frames", 1))
        animated = bool(getattr(source, "is_animated", False) and frame_count > 1)
        if animated:
            source.seek(0)
        image = ImageOps.exif_transpose(source)
        if image.width * image.height > MAX_PIXELS:
            raise ImageAnalysisError("Image dimensions are too large", code="image_too_large")

        rgba = image.convert("RGBA")
        icc_profile = image.info.get("icc_profile")
        icc_status = "absent"
        if icc_profile:
            try:
                input_profile = ImageCms.getOpenProfile(BytesIO(icc_profile))
                output_profile = ImageCms.createProfile("sRGB")
                converted = ImageCms.profileToProfile(
                    image.convert("RGB"),
                    input_profile,
                    output_profile,
                    outputMode="RGB",
                )
                converted.putalpha(rgba.getchannel("A"))
                rgba = converted
                icc_status = "converted_to_srgb"
            except (ImageCms.PyCMSError, OSError, ValueError) as exc:
                raise ImageAnalysisError("The embedded ICC profile could not be converted to sRGB", code="icc_conversion_failed") from exc

        return rgba, {
            "format": image_format,
            "animated": animated,
            "frame_count": frame_count,
            "selected_frame": 0,
            "animation_policy": ANIMATION_POLICY,
            "icc_profile": icc_status,
            "alpha_policy": ALPHA_POLICY,
        }
    except ImageAnalysisError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageAnalysisError("Upload a valid PNG, JPG, or WebP image", code="undecodable_image") from exc


def _validate_roi(roi: ROI, image_size: tuple[int, int]) -> ROI:
    if len(roi) != 4:
        raise ImageAnalysisError("ROI must contain x, y, width, and height", code="roi_incomplete")
    x, y, width, height = roi
    image_width, image_height = image_size
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ImageAnalysisError("ROI coordinates and dimensions must be positive", code="roi_invalid")
    if x + width > image_width or y + height > image_height:
        raise ImageAnalysisError("ROI must fit inside the uploaded image", code="roi_outside_image")
    return roi


def extract_palette(data: bytes, color_count: int = 5, roi: ROI | None = None) -> dict:
    if not data:
        raise ImageAnalysisError("The uploaded image is empty", code="empty_upload")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageAnalysisError("Image is larger than the 12 MB demo limit", code="upload_too_large")

    image, metadata = _decode_image(data)

    full_frame = _analyze_region(image, color_count)
    selected = full_frame
    if roi is not None:
        roi = _validate_roi(roi, image.size)
        x, y, width, height = roi
        selected = _analyze_region(image.crop((x, y, x + width, y + height)), color_count)

    source = "roi" if roi is not None else "full_frame"
    return {
        "width": selected["width"],
        "height": selected["height"],
        "original_width": image.width,
        "original_height": image.height,
        "analyzed_width": selected["width"],
        "analyzed_height": selected["height"],
        "analyzed_pixels": selected["analyzed_pixels"],
        "source": source,
        "roi": {"x": roi[0], "y": roi[1], "width": roi[2], "height": roi[3]} if roi else None,
        "model_version": MODEL_VERSION,
        "calibration_status": "uncalibrated",
        **metadata,
        "dominant": selected["dominant"],
        "palette": selected["palette"],
        "full_frame": {
            "analyzed_pixels": full_frame["analyzed_pixels"],
            "dominant": full_frame["dominant"],
            "palette": full_frame["palette"],
        },
    }
