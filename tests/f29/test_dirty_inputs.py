from app.core.f29.scoring import content_score
from tests.f29.samples import base_product


def _fields(hints):
    return [h["field"] for h in hints]


def test_content_score_non_string_description():
    score, _ = content_score({"description": 123, "title": "x", "images": []})
    assert score == 0.0


def test_content_score_string_image_no_duplicate_hint():
    _, hints = content_score(base_product(images="https://a/x.jpg"))
    assert "images" not in _fields(hints)


def test_content_score_int_images():
    content_score(base_product(images=5))


def test_content_score_duplicate_images_with_url_params():
    _, hints = content_score(base_product(images=[
        "https://res.cloudinary.com/demo/image.jpg?w=100",
        "https://res.cloudinary.com/demo/image.jpg?w=200",
    ]))
    assert "images" in _fields(hints)

