from app.core.f29.scoring import content_hints, normalize_image
from tests.f29.samples import base_product


def _fields(hints):
    return [h["field"] for h in hints]


def test_content_hints_non_string_description():
    hints = content_hints({"description": 123, "title": "x", "images": []})
    assert isinstance(hints, list)


def test_content_hints_string_image_no_duplicate_hint():
    hints = content_hints(base_product(images="https://a/x.jpg"))
    assert "images" not in _fields(hints)


def test_content_hints_int_images():
    content_hints(base_product(images=5))


def test_cloudinary_image_dedupe():
    u1 = "https://res.cloudinary.com/demo/image/upload/v1570979139/sample.jpg"
    u2 = "https://res.cloudinary.com/demo/image/upload/w_200,h_200/v1570979139/sample.png"
    assert normalize_image(u1) == normalize_image(u2) == "sample"
    hints = content_hints(base_product(images=[u1, u2]))
    assert "images" in _fields(hints)

