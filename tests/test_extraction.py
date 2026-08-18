from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageCms

from app.extraction import extract_palette


def test_extracts_dominant_color() -> None:
    image = Image.new("RGB", (100, 100), "#D8503F")
    for x in range(20):
        for y in range(100):
            image.putpixel((x, y), (20, 40, 220))
    output = BytesIO()
    image.save(output, format="PNG")

    result = extract_palette(output.getvalue(), color_count=2)

    assert result["dominant"]["hex"] == "#D8503F"
    assert result["dominant"]["share"] == 80.0
    assert len(result["palette"]) == 2


def test_palette_never_repeats_a_swatch_when_the_image_has_few_colors() -> None:
    image = Image.new("RGB", (64, 64), "#D92F26")
    for x in range(32):
        for y in range(64):
            image.putpixel((x, y), (33, 78, 156))
    output = BytesIO()
    image.save(output, format="PNG")

    result = extract_palette(output.getvalue(), color_count=5)
    hexes = [color["hex"] for color in result["palette"]]

    assert hexes == ["#D92F26", "#214E9C"] or hexes == ["#214E9C", "#D92F26"]
    assert len(hexes) == len(set(hexes))
    assert all(color["share"] > 0 for color in result["palette"])


def test_single_color_image_returns_one_swatch() -> None:
    output = BytesIO()
    Image.new("RGB", (64, 64), "#D92F26").save(output, format="PNG")

    result = extract_palette(output.getvalue(), color_count=5)

    assert [color["hex"] for color in result["palette"]] == ["#D92F26"]
    assert result["palette"][0]["share"] == 100.0


def test_roi_analysis_keeps_full_frame_palette_and_uses_selected_source() -> None:
    image = Image.new("RGB", (100, 100), "#D8503F")
    for x in range(20):
        for y in range(100):
            image.putpixel((x, y), (20, 40, 220))
    output = BytesIO()
    image.save(output, format="PNG")

    result = extract_palette(output.getvalue(), color_count=2, roi=(0, 0, 20, 100))

    assert result["source"] == "roi"
    assert result["roi"] == {"x": 0, "y": 0, "width": 20, "height": 100}
    assert result["dominant"]["hex"] == "#1428DC"
    assert result["full_frame"]["dominant"]["hex"] == "#D8503F"
    assert result["original_width"] == 100
    assert result["original_height"] == 100


def test_roi_must_fit_inside_image() -> None:
    image = Image.new("RGB", (10, 10), "#D8503F")
    output = BytesIO()
    image.save(output, format="PNG")

    with pytest.raises(ValueError, match="fit inside"):
        extract_palette(output.getvalue(), roi=(8, 8, 4, 4))


def test_exif_orientation_is_applied_before_palette_analysis() -> None:
    image = Image.new("RGB", (16, 8), "#D8503F")
    exif = image.getexif()
    exif[274] = 6
    output = BytesIO()
    image.save(output, format="PNG", exif=exif.tobytes())

    result = extract_palette(output.getvalue(), color_count=1)

    assert result["format"] == "PNG"
    assert (result["original_width"], result["original_height"]) == (8, 16)
    assert result["dominant"]["rgb"] == [216, 80, 63]


def test_upload_metadata_defines_alpha_icc_and_animation_behavior() -> None:
    image = Image.new("RGBA", (8, 8), (216, 80, 63, 255))
    for x in range(4):
        for y in range(8):
            image.putpixel((x, y), (20, 40, 220, 0))
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    output = BytesIO()
    image.save(output, format="PNG", icc_profile=profile)

    result = extract_palette(output.getvalue(), color_count=1)

    assert result["format"] == "PNG"
    assert result["animated"] is False
    assert result["frame_count"] == 1
    assert result["selected_frame"] == 0
    assert result["animation_policy"] == "first_frame_only"
    assert result["icc_profile"] == "converted_to_srgb"
    assert result["alpha_policy"].startswith("exclude_alpha_below_32")
    assert result["dominant"]["hex"] == "#D8503F"
    assert "transparent_pixels" in result["capture_quality"]["warnings"]


def test_capture_quality_flags_a_neutral_background_dominating_the_frame() -> None:
    image = Image.new("RGB", (100, 100), "#ECE1D8")
    for x in range(20):
        for y in range(100):
            image.putpixel((x, y), (208, 54, 43))
    output = BytesIO()
    image.save(output, format="PNG")

    result = extract_palette(output.getvalue(), color_count=2)

    assert result["capture_quality"]["status"] == "review"
    assert "neutral_background_dominant" in result["capture_quality"]["warnings"]


def test_animated_webp_uses_first_frame() -> None:
    output = BytesIO()
    Image.new("RGB", (8, 8), "#FF0000").save(
        output,
        format="WEBP",
        save_all=True,
        append_images=[Image.new("RGB", (8, 8), "#0000FF")],
        duration=100,
        loop=0,
    )

    result = extract_palette(output.getvalue(), color_count=1)

    assert result["format"] == "WEBP"
    assert result["animated"] is True
    assert result["frame_count"] == 2
    assert result["selected_frame"] == 0
    assert result["dominant"]["rgb"][0] > 240
    assert result["dominant"]["rgb"][2] < 20


def test_unsupported_decoded_format_is_rejected() -> None:
    output = BytesIO()
    Image.new("RGB", (8, 8), "#D8503F").save(output, format="GIF")

    with pytest.raises(ValueError, match="Decoded image format GIF is not supported"):
        extract_palette(output.getvalue())


@pytest.mark.parametrize(
    ("filename", "expected_hex"),
    [
        ("coral-cup.png", "#ECE1D8"),
        ("teal-crate.png", "#D5D4D4"),
        ("yellow-hard-hat.png", "#EDDECF"),
    ],
)
def test_demo_images_keep_full_frame_background_regression(filename: str, expected_hex: str) -> None:
    result = extract_palette((Path("example") / filename).read_bytes(), color_count=5)

    assert result["source"] == "full_frame"
    assert result["dominant"]["hex"] == expected_hex
