from io import BytesIO

from PIL import Image

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
